import os
import sys
import logging
from typing import Tuple, Optional
from django.db import transaction
from django.utils.text import slugify

from meet.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile

from

logger = logging.getLogger(__name__)

from isca_swim_scorer.
