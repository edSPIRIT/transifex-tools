import os
import requests
import json


class TransifexAPI:
    def __init__(self, api_token, organization, project):
        """Initialize the API client"""
        self.api_token = api_token
        self.organization = organization
        self.project = project
        self.base_url = "https://rest.api.transifex.com"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/vnd.api+json"
        }
        # Initialize session
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._last_response_text = None

        if not all([api_token, organization, project]):
            raise ValueError("Missing required parameters")

    def get_project_resources(self):
        """Get all resources for the project"""
        print(f"\nFetching resources for project: {self.project}")

        url = f"{self.base_url}/resources"
        params = {"filter[project]": f"o:{self.organization}:p:{self.project}"}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        return response.json()["data"]

    def _get_resource_translations(self, resource_id, language_code, filters=None):
        """Base method to get resource translations with custom filters"""
        print(
            f"Fetching translations for resource {resource_id}, language {language_code}"
        )

        translations = []
        base_url = f"{self.base_url}/resource_translations"

        # Extract the resource slug from the full resource_id
        resource_slug = (
            resource_id.split(":")[-1] if ":" in resource_id else resource_id
        )

        # Construct the full resource identifier
        full_resource = f"o:{self.organization}:p:{self.project}:r:{resource_slug}"

        # Base parameters
        params = {
            "filter[resource]": full_resource,
            "filter[language]": f"l:{language_code}",
            "include": "resource_string"  # This includes the source string content
        }

        # Add additional filters if provided
        if filters:
            params.update(filters)

        next_url = base_url
        while True:
            try:
                response = requests.get(
                    next_url if next_url != base_url else base_url,
                    headers=self.headers,
                    params=params if next_url == base_url else None
                )
                response.raise_for_status()
                data = response.json()

                # Process included resource strings
                resource_strings = {
                    rs['id']: rs['attributes'] 
                    for rs in data.get('included', [])
                    if rs['type'] == 'resource_strings'
                }

                # Process translations with their source strings
                for trans in data['data']:
                    resource_string_id = trans['relationships']['resource_string']['data']['id']
                    source_data = resource_strings.get(resource_string_id, {})
                    
                    # Get the translation from the main translation object
                    trans_strings = trans['attributes'].get('strings', {})
                    
                    # Combine source and translation data
                    trans['attributes']['strings'] = {
                        'other': source_data.get('strings', {}).get('other'),  # Source string
                        language_code: trans_strings.get('other')  # Translation
                    }
                    trans['attributes']['key'] = source_data.get('key', '')
                    trans['attributes']['context'] = source_data.get('context', '')

                translations.extend(data["data"])
                print(f"Fetched {len(translations)} strings so far...", end="\r")

                next_url = data.get("links", {}).get("next", "")
                if not next_url:
                    break

            except requests.exceptions.RequestException as e:
                print(f"\nError while fetching page: {e}")
                if hasattr(e.response, "text"):
                    print(f"Response: {e.response.text}")
                break

        print(f"\nCompleted fetching {len(translations)} strings")
        return translations

    def get_untranslated_strings(self, resource_id, language_code):
        """Get untranslated strings for a specific resource and language"""
        filters = {"filter[translated]": "false"}
        return self._get_resource_translations(resource_id, language_code, filters)

    def get_unreviewed_strings(self, resource_id, language_code):
        """Get unreviewed strings for a specific resource and language"""
        filters = {"filter[reviewed]": "false"}
        return self._get_resource_translations(resource_id, language_code, filters)

    def _get_resource_string_id(self, resource_id, key):
        """Get the resource string ID for a given key"""
        url = f"{self.base_url}/resource_strings"
        
        # Extract resource slug
        resource_slug = resource_id.split(":")[-1] if ":" in resource_id else resource_id
        full_resource = f"o:{self.organization}:p:{self.project}:r:{resource_slug}"
        
        params = {
            "filter[resource]": full_resource,
            "filter[key]": key
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['data']:
            return data['data'][0]['id']
        return None

    def _get_translation_id(self, resource_id, language_code, key):
        """Get the translation ID for a given resource string and language"""
        try:
            # First get the resource string ID
            string_id = self._get_resource_string_id(resource_id, key)
            if not string_id:
                return None
                
            # Construct the translation ID directly
            # Format: resource:string:language
            translation_id = f"{string_id}:l:{language_code}"
            return translation_id
            
        except Exception as e:
            print(f"Error getting translation ID: {e}")
            return None

    def update_translation(self, resource_id, language_code, key, translation):
        """Update a single translation"""
        try:
            # Get the translation ID
            translation_id = self._get_translation_id(resource_id, language_code, key)
            if not translation_id:
                print(f"Could not find translation ID for key: {key}")
                return None
                
            url = f"{self.base_url}/resource_translations/{translation_id}"
            
            data = {
                "data": {
                    "type": "resource_translations",
                    "id": translation_id,
                    "attributes": {
                        "strings": {
                            "other": translation
                        }
                    }
                }
            }
            
            response = requests.patch(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error updating translation for key {key}: {e}")
            if hasattr(e.response, "text"):
                print(f"Response: {e.response.text}")
            return None

    def review_translation(self, resource_id, language_code, key):
        """Mark a translation as reviewed"""
        try:
            # Get the translation ID
            translation_id = self._get_translation_id(resource_id, language_code, key)
            if not translation_id:
                print(f"Could not find translation ID for key: {key}")
                return None
                
            url = f"{self.base_url}/resource_translations/{translation_id}"
            
            data = {
                "data": {
                    "type": "resource_translations",
                    "id": translation_id,
                    "attributes": {
                        "reviewed": True
                    }
                }
            }
            
            response = requests.patch(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error reviewing translation for key {key}: {e}")
            return None

    def create_download_job(self, resource_id, language_code, file_type="PO", content_encoding="text", file_extension=".po"):
        """Create an async download job for a resource"""
        url = f"{self.base_url}/resource_translations_async_downloads"
        
        # Ensure language code is properly formatted
        if not language_code.startswith('l:'):
            language_code = f'l:{language_code}'
            
        # Extract resource slug from the full resource_id
        resource_slug = resource_id.split(":")[-1] if ":" in resource_id else resource_id
        
        # Construct the full resource identifier
        full_resource = f"o:{self.organization}:p:{self.project}:r:{resource_slug}"
        
        # Map file formats to API-accepted formats
        format_mapping = {
            "PO": "default",
            "KEYVALUEJSON": "json",
            "ANDROID": "default",
            "STRINGS": "default",
            "YAML_GENERIC": "default"
        }
        
        # Use mapped format or default if not found
        api_file_type = format_mapping.get(file_type, "default")
        
        payload = {
            "data": {
                "type": "resource_translations_async_downloads",
                "attributes": {
                    "content_encoding": content_encoding,
                    "file_type": "default",
                },
                "relationships": {
                    "language": {
                        "data": {
                            "type": "languages",
                            "id": language_code
                        }
                    },
                    "resource": {
                        "data": {
                            "type": "resources",
                            "id": full_resource
                        }
                    }
                }
            }
        }
        
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"Error details: {e.response.text}")
            raise

    def get_last_response_text(self):
        """Get the text content of the last response"""
        return self._last_response_text

    def check_download_status(self, job_id, output_path=None):
        """Check the status of an async download job and save the file if completed"""
        url = f"{self.base_url}/resource_translations_async_downloads/{job_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Print response status only
            print(f"Response status: {response.status_code}")
            
            # Check content type and strip parameters
            content_type = response.headers.get('content-type', '').lower().split(';')[0]
            print(f"Content type: {content_type}")
            
            # First check if it's a file response
            if content_type in ['application/octet-stream', 'text/x-po', 'text/plain', 'text/yaml']:
                if output_path:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    # Write in binary mode for octet-stream
                    mode = 'wb' if content_type == 'application/octet-stream' else 'w'
                    encoding = None if content_type == 'application/octet-stream' else 'utf-8'
                    
                    with open(output_path, mode, encoding=encoding) as f:
                        f.write(response.content if content_type == 'application/octet-stream' else response.text)
                    print(f"✓ Saved file directly: {output_path} ({os.path.getsize(output_path)} bytes)")
                    return {"data": {"attributes": {"status": "completed"}}}
                return response.content if content_type == 'application/octet-stream' else response.text
            
            # Try to parse response as JSON
            try:
                content = response.json()
                
                # If it's an API response (has data field)
                if isinstance(content, dict) and "data" in content:
                    # If download is completed and we have a URL
                    if (content["data"]["attributes"]["status"] == "completed" and 
                        output_path and 
                        content["data"]["attributes"].get("download_url")):
                        download_url = content["data"]["attributes"]["download_url"]
                        self.download_file(download_url, output_path)
                    return content
                
                # If it's a direct JSON translation file
                if isinstance(content, dict):
                    if output_path:
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(content, f, ensure_ascii=False, indent=2)
                        print(f"✓ Saved JSON translations: {output_path} ({os.path.getsize(output_path)} bytes)")
                        return {"data": {"attributes": {"status": "completed"}}}
                    return content
                
                raise ValueError(f"Unexpected JSON format: {content}")
                
            except json.JSONDecodeError:
                # If content looks like a PO file or YAML file
                content = response.text
                if content.strip().startswith('msgid') or content_type == 'text/yaml':
                    if output_path:
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"✓ Saved file: {output_path} ({os.path.getsize(output_path)} bytes)")
                        return {"data": {"attributes": {"status": "completed"}}}
                    return content
                raise ValueError(f"Unable to handle response content type: {content_type}")
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error {e.response.status_code}")
            if e.response.status_code != 200:
                print(f"Response: {e.response.text}")
            raise
        except Exception as e:
            print(f"Error: {type(e).__name__}")
            print(f"Error details: {str(e)}")
            raise

    def download_file(self, download_url, output_path, content=None):
        """Download a file from a given URL and save it to the specified path"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if content is not None:
                # Save content directly
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✓ Saved content directly to file ({os.path.getsize(output_path)} bytes)")
                return
            
            # Download from URL
            response = self.session.get(download_url)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"✓ Downloaded and saved file ({os.path.getsize(output_path)} bytes)")
            
        except Exception as e:
            print(f"Error saving file: {type(e).__name__}")
            raise
