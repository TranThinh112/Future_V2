import logging

log=logging.getLogger("alerts")
def alert(message):
    log.warning("alert",extra={"alert_message":message})
