import os
import json
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from bistro.cookbook import save_recipe_folder, load_all_recipes_from_dir, to_nextcloud_format, load_recipe_folder

class NextcloudSync:
    def __init__(self, server_url="", username="", password="", remote_folder="Recipes"):
        self.server_url = server_url.rstrip("/") if server_url else ""
        self.username = username
        self.password = password
        self.remote_folder = remote_folder.strip("/") if remote_folder else "Recipes"

    def get_auth(self):
        return (self.username, self.password)

    def get_webdav_url(self, path=""):
        path = path.lstrip("/")
        if path:
            return f"{self.server_url}/remote.php/dav/files/{self.username}/{self.remote_folder}/{path}"
        return f"{self.server_url}/remote.php/dav/files/{self.username}/{self.remote_folder}"

    def get_rest_api_url(self, path=""):
        path = path.lstrip("/")
        # Try index.php/apps/cookbook/api/v1 or apps/cookbook/api/v1
        base = f"{self.server_url}/index.php/apps/cookbook/api/v1"
        if path:
            return f"{base}/{path}"
        return base

    def test_connection(self, server_url=None, username=None, password=None, remote_folder=None):
        url = (server_url or self.server_url).rstrip("/")
        user = username or self.username
        pwd = password or self.password
        folder = (remote_folder or self.remote_folder).strip("/")

        if not url or not user or not pwd:
            return False, "Server URL, Username, and Password are required."

        auth = (user, pwd)
        # 1. Try REST API endpoint first
        try:
            api_url = f"{url}/index.php/apps/cookbook/api/v1/recipes"
            resp = requests.get(api_url, auth=auth, timeout=10)
            if resp.status_code == 200:
                return True, "Connected successfully via Nextcloud Cookbook REST API."
        except Exception:
            pass

        # 2. Try WebDAV endpoint
        dav_url = f"{url}/remote.php/dav/files/{user}/{folder}/"
        try:
            resp = requests.request("PROPFIND", dav_url, auth=auth, headers={"Depth": "1"}, timeout=10)
            if resp.status_code in [200, 207]:
                return True, "Connected successfully via Nextcloud WebDAV."
            elif resp.status_code == 404:
                # Root DAV folder exists, but Recipes folder doesn't exist yet -> attempt MKCOL or create
                parent_url = f"{url}/remote.php/dav/files/{user}/"
                parent_resp = requests.request("PROPFIND", parent_url, auth=auth, headers={"Depth": "1"}, timeout=10)
                if parent_resp.status_code in [200, 207]:
                    return True, f"Connected to Nextcloud. Folder '{folder}' will be created on sync."
            elif resp.status_code in [401, 403]:
                return False, "Authentication failed. Check username and password."
            return False, f"Server returned status code {resp.status_code}."
        except requests.exceptions.RequestException as e:
            return False, f"Connection failed: {str(e)}"

    def sync(self, server_url=None, username=None, password=None, remote_folder=None, local_recipes_dir=None):
        if server_url:
            self.server_url = server_url.rstrip("/")
        if username:
            self.username = username
        if password:
            self.password = password
        if remote_folder:
            self.remote_folder = remote_folder.strip("/")

        if not self.server_url or not self.username or not self.password:
            return False, {}, "Missing Nextcloud connection credentials."

        if not local_recipes_dir:
            return False, {}, "Local recipes directory not specified."

        os.makedirs(local_recipes_dir, exist_ok=True)
        stats = {"downloaded": 0, "uploaded": 0, "errors": 0}

        # Try REST API sync first
        api_success, api_stats, api_msg = self._sync_via_rest_api(local_recipes_dir)
        if api_success:
            return True, api_stats, api_msg

        # Fall back to WebDAV sync
        dav_success, dav_stats, dav_msg = self._sync_via_webdav(local_recipes_dir)
        return dav_success, dav_stats, dav_msg

    def _sync_via_rest_api(self, local_recipes_dir):
        auth = self.get_auth()
        api_recipes_url = f"{self.server_url}/index.php/apps/cookbook/api/v1/recipes"
        try:
            resp = requests.get(api_recipes_url, auth=auth, timeout=10)
            if resp.status_code != 200:
                # Try alternate path without index.php
                api_recipes_url = f"{self.server_url}/apps/cookbook/api/v1/recipes"
                resp = requests.get(api_recipes_url, auth=auth, timeout=10)
                if resp.status_code != 200:
                    return False, {}, "REST API not available."

            remote_recipes = resp.json()
            if not isinstance(remote_recipes, list):
                return False, {}, "Invalid REST API response."

            stats = {"downloaded": 0, "uploaded": 0, "errors": 0}
            local_recipes = load_all_recipes_from_dir(local_recipes_dir)
            local_map = {r.get('name', '').lower(): r for r in local_recipes}

            # 1. Download/Update remote recipes locally
            remote_names = set()
            for item in remote_recipes:
                r_id = item.get('id') or item.get('recipe_id')
                r_name = item.get('name') or item.get('strDrink') or item.get('strMeal')
                if not r_name:
                    continue
                remote_names.add(r_name.lower())

                # Check if we need full recipe
                if r_id:
                    detail_url = f"{api_recipes_url}/{r_id}"
                    d_resp = requests.get(detail_url, auth=auth, timeout=10)
                    if d_resp.status_code == 200:
                        recipe_data = d_resp.json()
                        save_recipe_folder(recipe_data, local_recipes_dir)
                        stats["downloaded"] += 1

            # 2. Upload local recipes that aren't on server
            for loc_name, loc_recipe in local_map.items():
                if loc_name not in remote_names:
                    nc_schema = to_nextcloud_format(loc_recipe)
                    post_resp = requests.post(api_recipes_url, auth=auth, json=nc_schema, timeout=10)
                    if post_resp.status_code in [200, 201]:
                        stats["uploaded"] += 1
                    else:
                        stats["errors"] += 1

            msg = f"Synced with Nextcloud Cookbook API (Downloaded {stats['downloaded']}, Uploaded {stats['uploaded']})."
            return True, stats, msg
        except Exception as e:
            return False, {}, f"REST API sync error: {e}"

    def _sync_via_webdav(self, local_recipes_dir):
        auth = self.get_auth()
        dav_base = self.get_webdav_url()
        stats = {"downloaded": 0, "uploaded": 0, "errors": 0}

        try:
            # Ensure remote base folder exists
            resp = requests.request("PROPFIND", f"{dav_base}/", auth=auth, headers={"Depth": "1"}, timeout=10)
            if resp.status_code == 404:
                # Try MKCOL to create remote folder
                mk_resp = requests.request("MKCOL", f"{dav_base}/", auth=auth, timeout=10)
                if mk_resp.status_code not in [201, 405]:
                    return False, stats, f"Failed to create remote directory '{self.remote_folder}'."
                resp = requests.request("PROPFIND", f"{dav_base}/", auth=auth, headers={"Depth": "1"}, timeout=10)

            if resp.status_code not in [200, 207]:
                return False, stats, f"WebDAV PROPFIND failed with status {resp.status_code}."

            # Parse WebDAV response XML to list remote recipe subdirectories
            remote_dirs = self._parse_propfind_subdirs(resp.content, dav_base)

            # 1. Download remote recipe folders to local_recipes_dir
            remote_folder_names = set()
            for r_dir_url, r_dir_name in remote_dirs:
                remote_folder_names.add(r_dir_name.lower())
                recipe_json_url = f"{r_dir_url.rstrip('/')}/recipe.json"
                rj_resp = requests.get(recipe_json_url, auth=auth, timeout=10)
                if rj_resp.status_code == 200:
                    try:
                        recipe_data = rj_resp.json()
                        folder_path = save_recipe_folder(recipe_data, local_recipes_dir)
                        stats["downloaded"] += 1

                        # Check and download image if present remotely
                        for img_name in ['full.jpg', 'full.png', 'thumb.jpg', 'thumb.png']:
                            img_url = f"{r_dir_url.rstrip('/')}/{img_name}"
                            img_resp = requests.get(img_url, auth=auth, timeout=10)
                            if img_resp.status_code == 200:
                                dest_img = os.path.join(folder_path, img_name)
                                with open(dest_img, 'wb') as f:
                                    f.write(img_resp.content)
                                break
                    except Exception as e:
                        stats["errors"] += 1

            # 2. Upload local recipe folders to WebDAV
            for entry in os.listdir(local_recipes_dir):
                local_folder_path = os.path.join(local_recipes_dir, entry)
                if os.path.isdir(local_folder_path) and os.path.exists(os.path.join(local_folder_path, "recipe.json")):
                    if entry.lower() not in remote_folder_names:
                        remote_sub_url = f"{dav_base}/{entry}/"
                        # Create directory remotely
                        requests.request("MKCOL", remote_sub_url, auth=auth, timeout=10)

                        # Upload recipe.json
                        local_json_path = os.path.join(local_folder_path, "recipe.json")
                        with open(local_json_path, 'rb') as f:
                            up_resp = requests.put(f"{remote_sub_url}recipe.json", auth=auth, data=f, timeout=10)
                            if up_resp.status_code in [200, 201, 204]:
                                stats["uploaded"] += 1

                        # Upload image if present
                        for img_name in ['full.jpg', 'full.png', 'thumb.jpg', 'thumb.png']:
                            local_img_path = os.path.join(local_folder_path, img_name)
                            if os.path.exists(local_img_path):
                                with open(local_img_path, 'rb') as f:
                                    requests.put(f"{remote_sub_url}{img_name}", auth=auth, data=f, timeout=10)
                                break

            msg = f"Synced with Nextcloud WebDAV (Downloaded {stats['downloaded']}, Uploaded {stats['uploaded']})."
            return True, stats, msg
        except Exception as e:
            return False, stats, f"WebDAV sync error: {e}"

    def _parse_propfind_subdirs(self, xml_content, dav_base_url):
        subdirs = []
        try:
            root = ET.fromstring(xml_content)
            # WebDAV namespace
            ns = {'d': 'DAV:'}
            for response in root.findall('d:response', ns):
                href = response.find('d:href', ns)
                if href is not None and href.text:
                    href_str = href.text.strip()
                    # Check if it's a collection (directory)
                    is_dir = False
                    propstat = response.find('d:propstat', ns)
                    if propstat is not None:
                        prop = propstat.find('d:prop', ns)
                        if prop is not None:
                            resourcetype = prop.find('d:resourcetype', ns)
                            if resourcetype is not None and resourcetype.find('d:collection', ns) is not None:
                                is_dir = True

                    if is_dir:
                        # Extract directory name
                        cleaned = href_str.rstrip('/')
                        dir_name = os.path.basename(cleaned)
                        if dir_name and dir_name != self.remote_folder and dir_name != os.path.basename(dav_base_url.rstrip('/')):
                            # Construct full URL for subdirectory
                            if href_str.startswith("http"):
                                full_url = href_str
                            else:
                                # Relative URL
                                scheme_host = "/".join(self.server_url.split('/')[:3])
                                full_url = f"{scheme_host}{href_str}"
                            subdirs.append((full_url, dir_name))
        except Exception as e:
            print(f"Error parsing PROPFIND XML: {e}")
        return subdirs
