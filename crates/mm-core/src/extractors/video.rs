use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use crate::extract::{ContentExtractor, ExtractError, L1Record};
use crate::hash;

pub struct VideoExtractor;

impl ContentExtractor for VideoExtractor {
    fn supports(&self, kind: &str) -> bool {
        kind == "video"
    }

    fn extract(&self, path: &Path) -> Result<L1Record, ExtractError> {
        let ext = path
            .extension()
            .map(|e| e.to_string_lossy().to_ascii_lowercase())
            .unwrap_or_default();

        let content_hash = hash::full_hash_mmap(path).map(|h| format!("{:016x}", h));

        let mut record = match ext.as_str() {
            "mp4" | "m4v" | "m4a" | "mov" => extract_mp4(path).unwrap_or_default(),
            "mkv" | "webm" => extract_matroska(path).unwrap_or_default(),
            _ => L1Record::default(),
        };

        record.content_hash = content_hash;
        Ok(record)
    }
}

fn extract_mp4(path: &Path) -> Result<L1Record, ExtractError> {
    let mut file = File::open(path)?;
    let ctx = mp4parse::read_mp4(&mut file)
        .map_err(|e| ExtractError::Unsupported(format!("mp4parse: {e:?}")))?;

    let mut record = L1Record::default();
    let mut has_audio = false;

    for track in &ctx.tracks {
        match track.track_type {
            mp4parse::TrackType::Video => {
                if let Some(tkhd) = &track.tkhd {
                    let w = tkhd.width >> 16;
                    let h = tkhd.height >> 16;
                    if w > 0 && h > 0 {
                        record.dimensions = Some(format!("{w}x{h}"));
                    }
                }

                if let Some(stsd) = &track.stsd {
                    for entry in &stsd.descriptions {
                        if let mp4parse::SampleEntry::Video(v) = entry {
                            record.video_codec = Some(codec_name_video(v));
                            if record.dimensions.is_none() && v.width > 0 && v.height > 0 {
                                record.dimensions = Some(format!("{}x{}", v.width, v.height));
                            }
                        }
                    }
                }

                if let (Some(dur), Some(ts)) = (track.duration, track.timescale)
                    && ts.0 > 0
                {
                    let secs = dur.0 as f64 / ts.0 as f64;
                    record.duration_s = Some(secs);
                }

                if let Some(stts) = &track.stts
                    && !stts.samples.is_empty()
                    && stts.samples[0].sample_delta > 0
                    && let Some(ts) = track.timescale
                {
                    let fps = ts.0 as f64 / stts.samples[0].sample_delta as f64;
                    record.fps = Some((fps * 1000.0).round() / 1000.0);
                }
            }
            mp4parse::TrackType::Audio => {
                has_audio = true;
                if let Some(stsd) = &track.stsd {
                    for entry in &stsd.descriptions {
                        if let mp4parse::SampleEntry::Audio(a) = entry {
                            record.audio_codec = Some(codec_name_audio(a));
                            break;
                        }
                    }
                }
            }
            _ => {}
        }
    }

    record.has_audio = Some(has_audio);
    Ok(record)
}

fn extract_matroska(path: &Path) -> Result<L1Record, ExtractError> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mkv = matroska::Matroska::open(reader)
        .map_err(|e| ExtractError::Unsupported(format!("matroska: {e}")))?;

    let mut record = L1Record::default();

    if let Some(dur) = mkv.info.duration {
        record.duration_s = Some(dur.as_secs_f64());
    }

    let mut has_audio = false;

    for track in &mkv.tracks {
        if track.is_video() {
            if let matroska::Settings::Video(ref v) = track.settings {
                record.dimensions = Some(format!("{}x{}", v.pixel_width, v.pixel_height));
            }
            record.video_codec = Some(mkv_codec_id_to_name(&track.codec_id));

            if let Some(dur) = track.default_duration {
                let nanos = dur.as_nanos() as f64;
                if nanos > 0.0 {
                    record.fps = Some((1_000_000_000.0 / nanos * 1000.0).round() / 1000.0);
                }
            }
        }
        if track.is_audio() {
            has_audio = true;
            record.audio_codec = Some(mkv_codec_id_to_name(&track.codec_id));
        }
    }

    record.has_audio = Some(has_audio);
    Ok(record)
}

fn codec_name_video(v: &mp4parse::VideoSampleEntry) -> String {
    match &v.codec_specific {
        mp4parse::VideoCodecSpecific::AVCConfig(_) => "h264".into(),
        mp4parse::VideoCodecSpecific::VPxConfig(_) => "vpx".into(),
        mp4parse::VideoCodecSpecific::AV1Config(_) => "av1".into(),
        mp4parse::VideoCodecSpecific::ESDSConfig(_) => "mpeg4".into(),
        mp4parse::VideoCodecSpecific::H263Config(_) => "h263".into(),
    }
}

fn codec_name_audio(a: &mp4parse::AudioSampleEntry) -> String {
    match &a.codec_specific {
        mp4parse::AudioCodecSpecific::ES_Descriptor(_) => "aac".into(),
        mp4parse::AudioCodecSpecific::FLACSpecificBox(_) => "flac".into(),
        mp4parse::AudioCodecSpecific::OpusSpecificBox(_) => "opus".into(),
        mp4parse::AudioCodecSpecific::ALACSpecificBox(_) => "alac".into(),
        mp4parse::AudioCodecSpecific::MP3 => "mp3".into(),
        mp4parse::AudioCodecSpecific::LPCM => "lpcm".into(),
    }
}

fn mkv_codec_id_to_name(codec_id: &str) -> String {
    match codec_id {
        "V_VP8" => "vp8".into(),
        "V_VP9" => "vp9".into(),
        "V_MPEG4/ISO/AVC" => "h264".into(),
        "V_MPEGH/ISO/HEVC" => "h265".into(),
        "V_AV1" => "av1".into(),
        "A_VORBIS" => "vorbis".into(),
        "A_OPUS" => "opus".into(),
        "A_AAC" | "A_AAC/MPEG4/LC" => "aac".into(),
        "A_FLAC" => "flac".into(),
        "A_PCM/INT/LIT" => "pcm".into(),
        _ => codec_id.to_lowercase(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supports_video_only() {
        let ext = VideoExtractor;
        assert!(ext.supports("video"));
        assert!(!ext.supports("image"));
        assert!(!ext.supports("code"));
        assert!(!ext.supports("audio"));
    }

    #[test]
    fn test_nonexistent_file() {
        let result = VideoExtractor.extract(Path::new("/nonexistent/video.mp4"));
        assert!(result.is_ok());
        let record = result.unwrap();
        assert!(record.dimensions.is_none());
        assert!(record.content_hash.is_none());
    }

    #[test]
    fn test_mkv_codec_mapping() {
        assert_eq!(mkv_codec_id_to_name("V_VP9"), "vp9");
        assert_eq!(mkv_codec_id_to_name("V_MPEG4/ISO/AVC"), "h264");
        assert_eq!(mkv_codec_id_to_name("A_OPUS"), "opus");
        assert_eq!(mkv_codec_id_to_name("UNKNOWN"), "unknown");
    }
}
