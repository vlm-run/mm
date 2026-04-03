//! Shared extraction helpers used by both video and audio extractors.

use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use crate::extract::{ExtractError, L1Record};

// ---------------------------------------------------------------------------
// Symphonia — MP3, WAV, FLAC, AAC, OGG/Vorbis, Opus
// ---------------------------------------------------------------------------

pub fn extract_symphonia(path: &Path) -> Result<L1Record, ExtractError> {
    use symphonia::core::formats::FormatOptions;
    use symphonia::core::io::MediaSourceStream;
    use symphonia::core::meta::MetadataOptions;
    use symphonia::core::probe::Hint;

    let file = File::open(path)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let mut hint = Hint::new();
    if let Some(ext) = path.extension() {
        hint.with_extension(&ext.to_string_lossy());
    }

    let probed = symphonia::default::get_probe()
        .format(
            &hint,
            mss,
            &FormatOptions::default(),
            &MetadataOptions::default(),
        )
        .map_err(|e| ExtractError::Unsupported(format!("symphonia: {e}")))?;

    let format = probed.format;
    let mut record = L1Record::default();

    // Find the best (default) audio track
    if let Some(track) = format.default_track() {
        let params = &track.codec_params;

        // Codec name
        record.audio_codec = Some(symphonia_codec_name(params.codec));

        // Duration
        if let Some(n_frames) = params.n_frames
            && let Some(tb) = params.time_base
        {
            let time = tb.calc_time(n_frames);
            let secs = time.seconds as f64 + time.frac;
            if secs > 0.0 {
                record.duration_s = Some(secs);
            }
        }

        record.has_audio = Some(true);
    }

    Ok(record)
}

fn symphonia_codec_name(codec: symphonia::core::codecs::CodecType) -> String {
    use symphonia::core::codecs;

    match codec {
        codecs::CODEC_TYPE_MP3 => "mp3".into(),
        codecs::CODEC_TYPE_AAC => "aac".into(),
        codecs::CODEC_TYPE_FLAC => "flac".into(),
        codecs::CODEC_TYPE_VORBIS => "vorbis".into(),
        codecs::CODEC_TYPE_OPUS => "opus".into(),
        codecs::CODEC_TYPE_PCM_S16LE
        | codecs::CODEC_TYPE_PCM_S16BE
        | codecs::CODEC_TYPE_PCM_S24LE
        | codecs::CODEC_TYPE_PCM_S24BE
        | codecs::CODEC_TYPE_PCM_S32LE
        | codecs::CODEC_TYPE_PCM_S32BE
        | codecs::CODEC_TYPE_PCM_F32LE
        | codecs::CODEC_TYPE_PCM_F32BE
        | codecs::CODEC_TYPE_PCM_F64LE
        | codecs::CODEC_TYPE_PCM_F64BE
        | codecs::CODEC_TYPE_PCM_U8 => "pcm".into(),
        _ => format!("unknown({:?})", codec),
    }
}

// ---------------------------------------------------------------------------
// MP4 container (mp4parse)
// ---------------------------------------------------------------------------

pub fn extract_mp4(path: &Path) -> Result<L1Record, ExtractError> {
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

                // For audio-only files (no video track), get duration from audio track
                if record.duration_s.is_none()
                    && let (Some(dur), Some(ts)) = (track.duration, track.timescale)
                    && ts.0 > 0
                {
                    let secs = dur.0 as f64 / ts.0 as f64;
                    record.duration_s = Some(secs);
                }
            }
            _ => {}
        }
    }

    record.has_audio = Some(has_audio);
    Ok(record)
}

// ---------------------------------------------------------------------------
// Matroska/WebM container
// ---------------------------------------------------------------------------

pub fn extract_matroska(path: &Path) -> Result<L1Record, ExtractError> {
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

// ---------------------------------------------------------------------------
// Codec name helpers
// ---------------------------------------------------------------------------

pub fn codec_name_video(v: &mp4parse::VideoSampleEntry) -> String {
    match &v.codec_specific {
        mp4parse::VideoCodecSpecific::AVCConfig(_) => "h264".into(),
        mp4parse::VideoCodecSpecific::VPxConfig(_) => "vpx".into(),
        mp4parse::VideoCodecSpecific::AV1Config(_) => "av1".into(),
        mp4parse::VideoCodecSpecific::ESDSConfig(_) => "mpeg4".into(),
        mp4parse::VideoCodecSpecific::H263Config(_) => "h263".into(),
    }
}

pub fn codec_name_audio(a: &mp4parse::AudioSampleEntry) -> String {
    match &a.codec_specific {
        mp4parse::AudioCodecSpecific::ES_Descriptor(_) => "aac".into(),
        mp4parse::AudioCodecSpecific::FLACSpecificBox(_) => "flac".into(),
        mp4parse::AudioCodecSpecific::OpusSpecificBox(_) => "opus".into(),
        mp4parse::AudioCodecSpecific::ALACSpecificBox(_) => "alac".into(),
        mp4parse::AudioCodecSpecific::MP3 => "mp3".into(),
        mp4parse::AudioCodecSpecific::LPCM => "lpcm".into(),
    }
}

pub fn mkv_codec_id_to_name(codec_id: &str) -> String {
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
