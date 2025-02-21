import hashlib
import logging
import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile

log = logging.getLogger(__name__)


def handle_uploaded_file(file_field: UploadedFile) -> Path:
    """
    Called by views.upload_slug() on student-form submit, if form is valid.

    Apparently it's good to go through the relative-path rigamarole below
    because using default_storage.save() is supposed to be good, and it needs a relative path.  🤔

    From reading django docs, there are nice some things django automatically does
    based on the uploaded size of the file (like saving to disk or memory).
    I can't remember if those features are active here, but am using standard approaches.

    But it still feels unnecessaryily messay. TODO: review and possibly refactor.
    """

    ## use storage directory directly since MEDIA_ROOT includes it
    staging_dir: Path = Path(default_storage.location)
    staging_dir.mkdir(parents=True, exist_ok=True)
    log.debug(f'staging_dir, ``{staging_dir}``')

    ## generate unique filename with original extension
    extension: str = Path(file_field.name).suffix
    filename: str = f'{uuid.uuid4().hex}{extension}'
    file_path: Path = staging_dir / filename
    log.debug(f'file_path, ``{file_path}``')

    ## compute relative path (since MEDIA_ROOT is the base, this is just the filename)
    relative_path: Path = file_path.relative_to(staging_dir)
    log.debug(f'relative_path, ``{relative_path}``')

    ## read file content and wrap in ContentFile
    file_content: bytes = file_field.read()
    content_file: ContentFile = ContentFile(file_content)

    ## convert the relative path to string for default_storage.save
    relative_path_str: str = str(relative_path)
    ## save the file using the default storage and get the saved path
    saved_path: str = default_storage.save(relative_path_str, content_file)
    log.debug(f'saved_path, ``{saved_path}``')

    ## return the absolute, resolved path to the saved file
    final_path: Path = (staging_dir / saved_path).resolve()
    log.debug(f'final_path, ``{final_path}``')
    return final_path


def make_checksum(saved_path: Path) -> tuple[str, str]:
    """
    Called by views.upload_slug() on student-form submit, if form is valid.
    Computes the checksum of the file-content and returns a tuple of the checksum_type and checksum.
    """
    with open(saved_path, 'rb') as f:
        file_content = f.read()
    checksum = hashlib.md5(file_content).hexdigest()
    checksum_type = 'md5'
    return checksum_type, checksum
