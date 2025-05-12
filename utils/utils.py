from passlib.context import CryptContext
from aiosmtplib import SMTP
from email.message import EmailMessage
from config.config import settings
import logging

log = logging.getLogger(__name__)

pwd_password = CryptContext(schemes=["bcrypt"])


def bcrypt(password: str):
    return pwd_password.hash(password)


def verify(plain_password, hashed_password):
    return pwd_password.verify(plain_password, hashed_password)


async def send_email(
    subject: str,
    body: str,
    to_email: str,
):
    message = EmailMessage()
    message["From"] = settings.SMTP_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        smtp = SMTP(hostname="smtp.gmail.com", port=465, use_tls=True)
        await smtp.connect()
        await smtp.login(settings.SMTP_EMAIL, settings.STMT_KEY)
        await smtp.send_message(message)
        await smtp.quit()
        log.info("Message Succsesfully sended on this gmail %s", to_email)
    except Exception as e:
        log.error(e)
