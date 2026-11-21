# SPDX-License-Identifier: AGPL-3.0-or-later
"""The mailer for a server without mail: sends nothing, and says so without addresses.

Without ``SNAPCOOK_SMTP_HOST`` no one can sign up with a password, so nothing
should try to send. If something does, the log says that a mail was not sent --
never to whom: Django's console backend would print whole mails, addresses and
links included, into the container log.
"""

from __future__ import annotations

import logging

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class MailOffBackend(BaseEmailBackend):
    def send_messages(self, email_messages) -> int:
        count = len(list(email_messages or []))
        if count:
            logger.warning("mail is not set up (SNAPCOOK_SMTP_HOST); %d mail(s) not sent", count)
        return 0
