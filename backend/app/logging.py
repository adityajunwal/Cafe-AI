import logging
import sys
from contextvars import ContextVar
from typing import Optional

request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
cafe_id_ctx: ContextVar[Optional[str]] = ContextVar("cafe_id", default=None)
session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


class StructuredLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        c_id = cafe_id_ctx.get()
        s_id = session_id_ctx.get()

        context_parts = []
        if req_id:
            context_parts.append(f"req={req_id}")
        if c_id:
            context_parts.append(f"cafe={c_id}")
        if s_id:
            context_parts.append(f"session={s_id}")

        ctx_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        record.msg = f"{record.msg}{ctx_str}"
        return super().format(record)


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = StructuredLogFormatter(
        "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


logger = logging.getLogger("cafe_ai_waiter")
