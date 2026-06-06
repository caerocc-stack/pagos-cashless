from datetime import datetime, timezone, timedelta

AR_TZ = timezone(timedelta(hours=-3))


def ahora_ar():
    return datetime.now(AR_TZ)
