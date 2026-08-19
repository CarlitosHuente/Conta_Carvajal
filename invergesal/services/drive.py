import io
import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']


def _credentials_paths():
    from django.conf import settings

    candidates = []
    configured = getattr(settings, 'INVERGESAL_GOOGLE_CREDENTIALS_FILE', None) or os.environ.get(
        'GOOGLE_APPLICATION_CREDENTIALS_FILE'
    )
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        candidates.append(path)
    candidates.append(Path(settings.BASE_DIR) / 'credenciales_google.json')
    return candidates


def get_drive_service():
    creds = None
    last_file = None
    for creds_file in _credentials_paths():
        last_file = creds_file
        if creds_file.exists():
            creds = service_account.Credentials.from_service_account_file(str(creds_file), scopes=SCOPES)
            break

    if creds is None:
        creds_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if not creds_json_str:
            from django.conf import settings
            creds_json_str = getattr(settings, 'INVERGESAL_GOOGLE_CREDENTIALS_JSON', '') or ''
        if creds_json_str:
            creds_info = json.loads(creds_json_str)
            creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            print(f'Error: no se encontró credenciales Drive ({last_file}) ni GOOGLE_APPLICATION_CREDENTIALS_JSON.')
            return None

    try:
        return build('drive', 'v3', credentials=creds)
    except Exception as exc:
        print(f'No se pudo construir el servicio de Drive: {exc}')
        return None


def find_file_by_name(name: str, folder_id: str):
    service = get_drive_service()
    if not service:
        return None

    try:
        query = f"name='{name}' and '{folder_id}' in parents and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, modifiedTime)').execute()
        files = response.get('files', [])
        if not files:
            return None
        return {'id': files[0]['id'], 'modifiedTime': files[0]['modifiedTime']}
    except Exception as exc:
        print(f'Error al buscar el archivo {name}: {exc}')
        return None


def list_xlsx_files(folder_id: str, exclude_names=None):
    """Lista Excel de la carpeta Drive. Si falla, devuelve lista vacía (no rompe el consolidado)."""
    exclude_names = set(exclude_names or [])
    service = get_drive_service()
    if not service:
        return []
    try:
        query = (
            f"'{folder_id}' in parents and "
            "mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' and "
            'trashed=false'
        )
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        return [f for f in response.get('files', []) if f.get('name') not in exclude_names]
    except Exception as exc:
        print(f'Error al listar Excel en Drive: {exc}')
        return []


def download_file(file_id: str) -> io.BytesIO | None:
    service = get_drive_service()
    if not service:
        return None

    try:
        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_buffer.seek(0)
        return file_buffer
    except Exception as exc:
        print(f'Error al descargar el archivo {file_id}: {exc}')
        return None


def upload_or_overwrite_file(name: str, folder_id: str, file_buffer: io.BytesIO):
    """Sube un archivo a Drive. Si ya existe, lo sobrescribe usando el id (dict) correcto."""
    service = get_drive_service()
    if not service:
        return False, 'No se pudo conectar al servicio de Drive.'

    try:
        file_info = find_file_by_name(name, folder_id)
        file_metadata = {'name': name}
        media = MediaIoBaseUpload(
            file_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True,
        )

        if file_info:
            service.files().update(
                fileId=file_info['id'],
                body=file_metadata,
                media_body=media,
                fields='id',
            ).execute()
            print(f"Archivo '{name}' actualizado con éxito.")
        else:
            file_metadata['parents'] = [folder_id]
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"Archivo '{name}' creado con éxito.")

        return True, f"Reporte '{name}' guardado en Google Drive con éxito."
    except HttpError as exc:
        error_message = f'Error de API al subir/sobrescribir el archivo: {exc}'
        print(error_message)
        return False, error_message
    except Exception as exc:
        error_message = f'Error al subir/sobrescribir el archivo: {exc}'
        print(error_message)
        return False, error_message
