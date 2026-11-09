"""Public errors contain no traceback, local paths, or provider internals."""
import logging
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger('pycollar.api')


def internal_error(message):
    logger.exception(message)
    return HTTPException(status_code=500, detail=message)


async def unexpected_error(request, error):
    logger.error('Unhandled %s %s', request.method, request.url.path,
                 exc_info=(type(error), error, error.__traceback__))
    return JSONResponse(status_code=500, content={'detail': '服务处理失败，请稍后重试；详细原因已记录到后端日志。'})
