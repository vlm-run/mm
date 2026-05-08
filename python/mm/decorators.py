import time
from functools import wraps


def retry(
    retries=3,
    delay=1,
    backoff=1,
    exceptions=(Exception,),
):
    """
    Simple retry decorator.

    Args:
        retries (int): Number of retry attempts.
        delay (float): Initial delay between retries.
        backoff (float): Multiplier for exponential backoff.
        exceptions (tuple): Exceptions to catch.

    Example:
        @retry(retries=5, delay=2, backoff=2)
        def fetch():
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay

            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions:
                    if attempt == retries:
                        raise

                    time.sleep(current_delay)
                    current_delay *= backoff

        return wrapper

    return decorator
