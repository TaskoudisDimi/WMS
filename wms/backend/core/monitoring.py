"""Error tracking with Sentry (sentry.io). Off unless SENTRY_DSN is set."""
import os


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,          # no emails / IPs / cookies sent to Sentry
    )                                    # the FastAPI integration reports 5xx only
