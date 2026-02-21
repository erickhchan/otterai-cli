import json
import xml.etree.ElementTree as ET

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder


class OtterAIError(Exception):
    pass


class OtterAIClient:
    API_BASE_URL = "https://otter.ai/forward/api/v1/"
    S3_BASE_URL = "https://s3.us-west-2.amazonaws.com/"
    DEFAULT_TIMEOUT = 30

    def __init__(self):
        self._session = requests.Session()
        self._userid = None
        self._cookies = None

    def _require_userid(self):
        if not self._userid:
            raise OtterAIError("userid is invalid")

    def _authed_headers(self):
        return {
            "x-csrftoken": self._cookies.get("csrftoken", ""),
            "referer": "https://otter.ai/",
        }

    def _handle_response(self, response, data=None):
        if data:
            return {"status": response.status_code, "data": data}
        try:
            return {"status": response.status_code, "data": response.json()}
        except ValueError:
            return {"status": response.status_code, "data": {}}

    def login(self, username, password):
        auth_url = self.API_BASE_URL + "login"

        payload = {"username": username}

        self._session.auth = (username, password)

        response = self._session.get(
            auth_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        self._userid = response.json()["userid"]
        self._cookies = response.cookies.get_dict()

        return self._handle_response(response)

    def get_user(self):
        self._require_userid()
        user_url = self.API_BASE_URL + "user"

        response = self._session.get(user_url, timeout=self.DEFAULT_TIMEOUT)

        return self._handle_response(response)

    def get_speakers(self):
        self._require_userid()
        speakers_url = self.API_BASE_URL + "speakers"

        payload = {"userid": self._userid}

        response = self._session.get(
            speakers_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    # Note: The API does not support pagination (offset/cursor). The only way
    # to retrieve more speeches is to increase page_size.
    def get_speeches(self, folder=0, page_size=45, source="owned"):
        self._require_userid()
        speeches_url = self.API_BASE_URL + "speeches"

        payload = {
            "userid": self._userid,
            "folder": folder,
            "page_size": page_size,
            "source": source,
        }

        response = self._session.get(
            speeches_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def get_speech(self, speech_id):
        self._require_userid()
        speech_url = self.API_BASE_URL + "speech"

        payload = {"userid": self._userid, "otid": speech_id}

        response = self._session.get(
            speech_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def set_speech_title(self, speech_id, title):
        self._require_userid()
        set_title_url = self.API_BASE_URL + "set_speech_title"

        payload = {"otid": speech_id, "title": title}

        response = self._session.get(
            set_title_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def query_speech(self, query, speech_id, size=500):
        self._require_userid()
        query_speech_url = self.API_BASE_URL + "advanced_search"

        payload = {"query": query, "size": size, "otid": speech_id}

        response = self._session.get(
            query_speech_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def upload_speech(self, file_name, content_type="audio/mp4"):
        self._require_userid()
        speech_upload_params_url = self.API_BASE_URL + "speech_upload_params"
        speech_upload_prod_url = self.S3_BASE_URL + "speech-upload-prod"
        finish_speech_upload = self.API_BASE_URL + "finish_speech_upload"

        payload = {"userid": self._userid}
        response = self._session.get(
            speech_upload_params_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        response_json = response.json()
        params_data = response_json["data"]

        prep_req = requests.Request("OPTIONS", speech_upload_prod_url).prepare()
        prep_req.headers["Accept"] = "*/*"
        prep_req.headers["Connection"] = "keep-alive"
        prep_req.headers["Origin"] = "https://otter.ai"
        prep_req.headers["Referer"] = "https://otter.ai/"
        prep_req.headers["Access-Control-Request-Method"] = "POST"

        response = self._session.send(prep_req, timeout=self.DEFAULT_TIMEOUT)

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        fields = {}
        params_data["success_action_status"] = str(
            params_data["success_action_status"]
        )
        del params_data["form_action"]
        fields.update(params_data)

        with open(file_name, mode="rb") as fh:
            fields["file"] = (file_name, fh, content_type)
            multipart_data = MultipartEncoder(fields=fields)

            response = requests.post(
                speech_upload_prod_url,
                data=multipart_data,
                headers={"Content-Type": multipart_data.content_type},
                timeout=self.DEFAULT_TIMEOUT,
            )

        if response.status_code != 201:
            return self._handle_response(response)

        xmltree = ET.ElementTree(ET.fromstring(response.text))
        xmlroot = xmltree.getroot()
        location = xmlroot[0].text
        bucket = xmlroot[1].text
        key = xmlroot[2].text

        payload = {
            "bucket": bucket,
            "key": key,
            "language": "en",
            "country": "us",
            "userid": self._userid,
        }
        response = self._session.get(
            finish_speech_upload, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def download_speech(self, speech_id, name=None, fileformat="txt,pdf,mp3,docx,srt"):
        self._require_userid()
        download_speech_url = self.API_BASE_URL + "bulk_export"

        payload = {"userid": self._userid}

        data = {"formats": fileformat, "speech_otid_list": [speech_id]}
        headers = self._authed_headers()
        response = self._session.post(
            download_speech_url,
            params=payload,
            headers=headers,
            data=data,
            timeout=self.DEFAULT_TIMEOUT,
        )

        filename = (
            (name if name is not None else speech_id)
            + "."
            + ("zip" if "," in fileformat else fileformat)
        )
        if response.ok:
            with open(filename, "wb") as f:
                f.write(response.content)
        else:
            raise OtterAIError(
                f"Got response status {response.status_code} when attempting to download {speech_id}"
            )
        return self._handle_response(response, data={"filename": filename})

    def move_to_trash_bin(self, speech_id):
        self._require_userid()
        move_to_trash_bin_url = self.API_BASE_URL + "move_to_trash_bin"

        payload = {"userid": self._userid}

        data = {"otid": speech_id}
        headers = self._authed_headers()
        response = self._session.post(
            move_to_trash_bin_url,
            params=payload,
            headers=headers,
            data=data,
            timeout=self.DEFAULT_TIMEOUT,
        )

        return self._handle_response(response)

    def create_speaker(self, speaker_name):
        self._require_userid()
        create_speaker_url = self.API_BASE_URL + "create_speaker"

        payload = {"userid": self._userid}

        data = {"speaker_name": speaker_name}
        headers = self._authed_headers()
        response = self._session.post(
            create_speaker_url,
            params=payload,
            headers=headers,
            data=data,
            timeout=self.DEFAULT_TIMEOUT,
        )

        return self._handle_response(response)

    def set_transcript_speaker(
        self,
        speech_id,
        transcript_uuid,
        speaker_id,
        speaker_name,
        create_speaker=False,
    ):
        self._require_userid()
        set_speaker_url = self.API_BASE_URL + "set_transcript_speaker"

        payload = {
            "speech_otid": speech_id,
            "transcript_uuid": transcript_uuid,
            "speaker_name": speaker_name,
            "userid": self._userid,
            "create_speaker": str(create_speaker).lower(),
            "speaker_id": speaker_id,
        }

        headers = self._authed_headers()
        response = self._session.get(
            set_speaker_url,
            params=payload,
            headers=headers,
            timeout=self.DEFAULT_TIMEOUT,
        )

        return self._handle_response(response)

    def get_notification_settings(self):
        self._require_userid()
        notification_settings_url = self.API_BASE_URL + "get_notification_settings"
        response = self._session.get(
            notification_settings_url, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def list_groups(self):
        self._require_userid()
        list_groups_url = self.API_BASE_URL + "list_groups"

        payload = {"userid": self._userid}

        response = self._session.get(
            list_groups_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def get_folders(self):
        self._require_userid()
        folders_url = self.API_BASE_URL + "folders"

        payload = {"userid": self._userid}

        response = self._session.get(
            folders_url, params=payload, timeout=self.DEFAULT_TIMEOUT
        )

        return self._handle_response(response)

    def create_folder(self, folder_name):
        self._require_userid()
        create_folder_url = self.API_BASE_URL + "create_folder"

        payload = {"userid": self._userid}
        data = {"folder_name": folder_name}
        headers = self._authed_headers()
        response = self._session.post(
            create_folder_url,
            params=payload,
            headers=headers,
            data=data,
            timeout=self.DEFAULT_TIMEOUT,
        )

        return self._handle_response(response)

    def rename_folder(self, folder_id, new_name):
        self._require_userid()
        rename_folder_url = self.API_BASE_URL + "rename_folder"

        payload = {"userid": self._userid, "folder_id": folder_id}
        data = {"new_name": new_name}
        headers = self._authed_headers()
        response = self._session.post(
            rename_folder_url,
            params=payload,
            headers=headers,
            data=data,
            timeout=self.DEFAULT_TIMEOUT,
        )

        return self._handle_response(response)

    def add_folder_speeches(self, folder_id, speech_ids):
        self._require_userid()
        add_folder_speeches_url = self.API_BASE_URL + "add_folder_speeches"

        if isinstance(speech_ids, str):
            speech_ids = [speech_ids]

        payload = {"userid": self._userid, "folder_id": folder_id}
        headers = self._authed_headers()

        results = []
        for speech_id in speech_ids:
            data = {"speech_otid_list": speech_id}
            response = self._session.post(
                add_folder_speeches_url,
                params=payload,
                headers=headers,
                data=data,
                timeout=self.DEFAULT_TIMEOUT,
            )
            results.append(self._handle_response(response))

        return results[-1] if results else {"status": 200}
