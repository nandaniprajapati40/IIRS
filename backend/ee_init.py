import ee
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_EE_INITIALIZED = False

def init_ee():
    global _EE_INITIALIZED

    if _EE_INITIALIZED:
        return

    try:
        project_id = os.getenv("EE_PROJECT_ID")

        if project_id:
            ee.Initialize(project=project_id)
        else:
            ee.Initialize()

        ee.Number(1).getInfo()
        _EE_INITIALIZED = True
        logger.info(f"Earth Engine initialized with project: {project_id}")

    except Exception as e:
        logger.error("Earth Engine initialization failed")
        raise RuntimeError(
            "Earth Engine not authenticated or project not registered.\n"
            "Run: earthengine authenticate\n"
            f"Error: {e}"
        )