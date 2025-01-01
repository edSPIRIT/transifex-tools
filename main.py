import argparse
from collections import defaultdict
from src.transifex_api import TransifexAPI
from src.csv_handler import save_to_csv
from src.config import load_config
from src.translation_handler import TranslationHandler, save_translations
from src.validation_handler import ValidationHandler
import os
import csv
import json
from src.review_handler import ReviewHandler
import requests
import time
import yaml


def get_cached_strings(output_dir, mode, languages):
    """Get strings from cached CSV files if they exist"""
    cached_strings = defaultdict(lambda: defaultdict(list))

    for lang in languages:
        filename = os.path.join(output_dir, f"{mode}_{lang}.csv")
        if os.path.exists(filename):
            print(f"Found cached {mode} strings for {lang}")
            with open(filename, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    string_info = {
                        "key": row["String Key"],
                        "source": row["Source String"],
                        "context": row["Context"],
                    }
                    
                    # Add translation for unreviewed mode
                    if mode == "unreviewed" and "Translation" in row:
                        string_info["translation"] = row["Translation"]
                        
                    cached_strings[lang][row["Resource"]].append(string_info)

    return cached_strings


def fetch_strings(api, resources, config, mode="untranslated", force_download=False):
    """Fetch strings based on mode (untranslated or unreviewed)"""
    output_dir = "output"

    # Check for cached files if not forcing download
    if not force_download:
        cached_strings = get_cached_strings(
            output_dir, mode, config["target_languages"]
        )
        if cached_strings:
            print(f"Using cached {mode} strings")
            return cached_strings

    # If no cache or force_download, fetch from API
    print(f"Downloading {mode} strings from Transifex")
    strings_by_lang = defaultdict(lambda: defaultdict(list))

    for resource in resources:
        resource_name = resource["attributes"]["name"]
        resource_id = resource["id"]

        print(f"\nProcessing resource: {resource_name}")

        for lang in config["target_languages"]:
            try:
                # Get strings based on mode
                if mode == "untranslated":
                    translations = api.get_untranslated_strings(resource_id, lang)
                else:  # unreviewed
                    translations = api.get_unreviewed_strings(resource_id, lang)

                # Store strings
                for trans in translations:
                    if not trans.get("attributes"):
                        print(f"Warning: No attributes found in translation: {trans}")
                        continue

                    attributes = trans["attributes"]
                    strings = attributes.get("strings", {})
                    
                    # For unreviewed strings, we get both source and translation
                    source = strings.get("other")  # Source string
                    translation = strings.get(lang)  # Translation in target language
                    
                    if source:  # We always need the source
                        print(f"Debug - Processing string:")
                        print(f"Source: {source}")
                        print(f"Translation: {translation}")
                        
                        strings_by_lang[lang][resource_name].append(
                            {
                                "key": attributes.get("key", ""),
                                "source": source,
                                "translation": translation or "",  # Use empty string if no translation
                                "context": attributes.get("context", ""),
                            }
                        )

            except Exception as e:
                print(f"Error processing {resource_name} for language {lang}: {e}")
                continue

    # Save the newly downloaded strings
    for lang in strings_by_lang:
        save_to_csv(strings_by_lang, lang, mode)

    return strings_by_lang


def translate_strings(
    api, strings_by_lang, resources_map, mode="untranslated", update_transifex=False
):
    """Process strings based on mode and optionally update Transifex"""
    translations_dir = "translations"

    for lang in strings_by_lang:
        print(f"\nProcessing translations for {lang}")
        translator = TranslationHandler(lang)

        for resource_name, strings in strings_by_lang[lang].items():
            print(f"\nProcessing {resource_name}...")
            results = translator.process_strings(strings, mode)

            # Save results to translations directory
            save_translations(results, lang, resource_name, translations_dir)

        if update_transifex:
            update_translations_from_files(api, resources_map, translations_dir)


def update_translations_from_files(api, resources_map, translations_dir="translations"):
    """Update translations in Transifex from saved translation files"""
    if not os.path.exists(translations_dir):
        print(f"No translations directory found at {translations_dir}")
        return

    # Get all JSON files in the translations directory (one per language)
    translation_files = [f for f in os.listdir(translations_dir) if f.endswith(".json")]

    for file in translation_files:
        try:
            # Extract language from filename
            lang = file.replace(".json", "")

            # Load all translations for this language
            with open(os.path.join(translations_dir, file), "r", encoding="utf-8") as f:
                all_translations = json.load(f)

            # Process each resource's translations
            for resource_name, translations in all_translations.items():
                if resource_name not in resources_map:
                    print(f"Warning: Resource {resource_name} not found in project")
                    continue

                resource_id = resources_map[resource_name]
                print(
                    f"\nProcessing {len(translations)} translations for {resource_name} ({lang})"
                )

                # Update translations
                for trans in translations:
                    try:
                        if trans["action"] == "translate":
                            api.update_translation(
                                resource_id, lang, trans["key"], trans["translation"]
                            )
                            print(f"Updated translation for key: {trans['key']}")
                        elif trans["action"] == "review" and trans.get(
                            "approved", False
                        ):
                            api.review_translation(resource_id, lang, trans["key"])
                            print(f"Marked as reviewed for key: {trans['key']}")
                    except Exception as e:
                        print(f"Error processing key {trans['key']}: {e}")

        except Exception as e:
            print(f"Error processing file {file}: {e}")


def load_transifex_config():
    """Load resource configurations from transifex.yml"""
    print("\n=== Loading Transifex Configuration ===")
    with open('transifex.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create a mapping of resource patterns to their configurations
    resource_configs = {}
    for filter_config in config['git']['filters']:
        print(f"\nProcessing filter config:")
        print(f"Filter type: {filter_config['filter_type']}")
        
        # For dir type filters
        if filter_config['filter_type'] == 'dir':
            # Extract the project name from the source_file_dir
            # Example: translations/AudioXBlock/audio/conf/locale/en/ -> AudioXBlock
            parts = filter_config['source_file_dir'].split('/')
            print(f"Dir parts: {parts}")
            if len(parts) > 2:
                project_name = parts[1]
                print(f"Adding dir config for: {project_name}")
                resource_configs[project_name] = {
                    'type': 'dir',
                    'format': filter_config['file_format'],
                    'path_expression': filter_config['translation_files_expression']
                }
        
        # For file type filters
        elif filter_config['filter_type'] == 'file':
            # Extract project name from source_file
            # Example: translations/frontend-app-account/src/i18n/transifex_input.json -> frontend-app-account
            parts = filter_config['source_file'].split('/')
            print(f"File parts: {parts}")
            if len(parts) > 2:
                project_name = parts[1]
                print(f"Adding file config for: {project_name}")
                resource_configs[project_name] = {
                    'type': 'file',
                    'format': filter_config['file_format'],
                    'path_expression': filter_config['translation_files_expression']
                }
    
    print("\n=== Final Resource Configurations ===")
    for name, config in resource_configs.items():
        print(f"{name}: {config}")
    
    return resource_configs


def fetch_strings_async(api: TransifexAPI, resources, config, mode="untranslated", force_download=False):
    """Fetch strings asynchronously and save them in the correct directory structure"""
    
    # Load resource configurations from transifex.yml
    resource_configs = load_transifex_config()
    
    # Create normalized maps for better matching
    normalized_configs = {}
    for key, value in resource_configs.items():
        normalized_key = key.lower().replace('_', '-').replace('.', '-')
        normalized_configs[normalized_key] = (key, value)
        # Also add the key without any suffix
        base_key = normalized_key.split('-input')[0]
        if base_key != normalized_key:
            normalized_configs[base_key] = (key, value)
    
    # Track configured and processed resources
    configured_resources = set(resource_configs.keys())
    processed_resources = set()
    
    print("\n=== Debug: Resource Information ===")
    print("\nConfigured Resources in transifex.yml:")
    for key in sorted(configured_resources):
        print(f"✓ {key}")
    
    print("\nAvailable Resources from Transifex:")
    for resource in resources:
        print(f"• Name: {resource['attributes']['name']}")
        print(f"  ID: {resource['id']}")
    
    # Create base output directory
    base_dir = os.getcwd()
    
    # Track all jobs
    download_jobs = []
    completed_jobs = []
    failed_jobs = []
    skipped_jobs = []
    
    print("\n=== Processing Resources ===")
    
    # Process resources
    for resource in resources:
        resource_name = resource["attributes"]["name"]
        resource_id = resource["id"]
        
        print(f"\n=== Processing Resource: {resource_name} ===")
        
        # Try different variations of the resource name
        variations = []
        
        # Original name without extension
        base_name = resource_name.split('.')[0]
        variations.append(base_name)
        
        # Normalized version
        normalized_name = base_name.lower().replace('_', '-')
        variations.append(normalized_name)
        
        # Handle path-based names
        if '/' in normalized_name:
            parts = normalized_name.split('/')
            variations.extend(parts)
            # Also try parts without -input suffix
            variations.extend([p.split('-input')[0] for p in parts if '-input' in p])
        
        # Try without -js suffix if present
        if normalized_name.endswith('-js'):
            variations.append(normalized_name[:-3])
        
        print(f"Trying variations: {variations}")
        
        # Try to find a match
        matched_config = None
        matched_name = None
        
        for var in variations:
            if var in normalized_configs:
                matched_name = normalized_configs[var][0]
                matched_config = normalized_configs[var][1]
                print(f"Found match: {var} -> {matched_name}")
                break
        
        if not matched_config:
            print(f"❌ No configuration found for {resource_name} in transifex.yml")
            print(f"Tried variations: {variations}")
            failed_jobs.append({
                "resource": resource_name,
                "reason": f"No configuration in transifex.yml (tried: {variations})"
            })
            continue
        
        print(f"✓ Found configuration for {matched_name}")
        processed_resources.add(matched_name)
        
        for lang in config["target_languages"]:
            # Determine output path based on the configuration
            if matched_config['type'] == 'dir':
                relative_path = matched_config['path_expression'].replace('<lang>', lang)
                
                if matched_config['format'] == 'PO':
                    if normalized_name.endswith('-js'):
                        relative_path = os.path.join(os.path.dirname(relative_path), 'LC_MESSAGES', 'djangojs.po')
                    else:
                        relative_path = os.path.join(os.path.dirname(relative_path), 'LC_MESSAGES', 'django.po')
            else:  # file type
                relative_path = matched_config['path_expression'].replace('<lang>', lang)
            
            output_path = os.path.join(base_dir, relative_path)
            
            if not force_download and os.path.exists(output_path):
                print(f"⏭️ Skipping existing file: {relative_path}")
                skipped_jobs.append({
                    "resource": resource_name,
                    "reason": "File already exists"
                })
                continue
            
            try:
                print(f"\n🔄 Creating job for {resource_name} - {lang}")
                print(f"Format: {matched_config['format']}")
                print(f"Output path: {output_path}")
                
                # Create download job
                job_data = api.create_download_job(
                    resource_id,
                    lang,
                    file_type=matched_config['format'],
                    content_encoding="text",
                    file_extension=os.path.splitext(relative_path)[1] or ".po"
                )
                
                job_id = job_data["data"]["id"]
                print(f"✓ Job created with ID: {job_id}")
                
                download_jobs.append({
                    "job_id": job_id,
                    "resource": resource_name,
                    "language": lang,
                    "output_path": output_path,
                    "file_type": matched_config['format']
                })
                
            except Exception as e:
                print(f"❌ Error creating download job for {resource_name} - {lang}")
                print(f"Error type: {type(e).__name__}")
                print(f"Error details: {str(e)}")
                failed_jobs.append({
                    "resource": resource_name,
                    "language": lang,
                    "reason": f"Job creation failed: {type(e).__name__} - {str(e)}"
                })
                continue
    
    # Give some time for jobs to initialize
    if download_jobs:
        print(f"\n⏳ Waiting 15 seconds for jobs to initialize...")
        time.sleep(15)
    
    # Process jobs sequentially
    print(f"\n=== Processing {len(download_jobs)} download jobs ===")
    
    for job in download_jobs:
        retries = 0
        max_retries = 3
        job_failed = False
        
        while retries < max_retries and not job_failed:
            try:
                print(f"\n=== Processing: {job['resource']} ({job['language']}) ===")
                print(f"Job ID: {job['job_id']}")
                print(f"Attempt: {retries + 1}/{max_retries}")
                
                status_data = api.check_download_status(job["job_id"], job["output_path"])
                
                # Check status from response
                status = status_data["data"]["attributes"]["status"]
                print(f"Status: {status}")
                
                if status == "failed":
                    print(f"❌ Download failed")
                    if "errors" in status_data:
                        print(f"Error details: {status_data['errors']}")
                    failed_jobs.append({
                        "resource": job['resource'],
                        "language": job['language'],
                        "reason": f"Download failed with status: {status}"
                    })
                    job_failed = True
                    break
                
                elif status == "completed":
                    completed_jobs.append(job)
                    break
                
                elif status == "processing":
                    print("⏳ Still processing...")
                    time.sleep(5)  # Wait before next check
                    continue
                
            except Exception as e:
                print(f"❌ Error: {type(e).__name__}")
                print(f"Error details: {str(e)}")
                retries += 1
                if retries < max_retries:
                    print(f"⚠️ Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    failed_jobs.append({
                        "resource": job['resource'],
                        "language": job['language'],
                        "reason": f"Failed after {retries} attempts: {type(e).__name__} - {str(e)}"
                    })
                    job_failed = True
    
    # Compare configured vs processed resources
    unprocessed_resources = configured_resources - processed_resources
    
    print(f"\n=== Resource Processing Summary ===")
    print(f"Total configurations in transifex.yml: {len(configured_resources)}")
    print(f"Total resources processed: {len(processed_resources)}")
    print(f"Total resources not processed: {len(unprocessed_resources)}")
    
    if unprocessed_resources:
        print("\n=== Resources Not Processed ===")
        for resource in sorted(unprocessed_resources):
            print(f"• {resource}")
    
    print(f"\n=== Final Summary ===")
    print(f"✓ Successfully completed: {len(completed_jobs)}")
    print(f"❌ Failed: {len(failed_jobs)}")
    print(f"⏭️ Skipped: {len(skipped_jobs)}")
    
    if failed_jobs:
        print("\n=== Failed Jobs Details ===")
        for job in failed_jobs:
            print(f"\n❌ Resource: {job['resource']}")
            print(f"   Language: {job.get('language', 'N/A')}")
            print(f"   Reason: {job['reason']}")
    
    return completed_jobs


def format_json_translations(content):
    """Format JSON translations to the desired format"""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return content

    formatted = {}
    for key, value in content.items():
        # First unescape the key by removing all backslashes
        clean_key = key.replace('\\\\', '').replace('\\.', '.')
        
        # If value is an object with 'string' field, use that
        if isinstance(value, dict) and 'string' in value:
            formatted[clean_key] = value['string']
        else:
            formatted[clean_key] = value
            
    return formatted

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
        
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # For binary files (like application/octet-stream)
            if content_type == 'application/octet-stream':
                with open(output_path, 'wb') as f:
                    f.write(response.content)
            # For text files (json, po, yaml, etc)
            else:
                content = response.text
                
                # If it looks like JSON, try to fix and parse it
                if content.strip().startswith('{'):
                    try:
                        # Try to parse as is first
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        print("Invalid JSON detected, attempting to fix quotes...")
                        # Fix unescaped quotes in JSON values
                        import re
                        
                        def fix_json_string(match):
                            # Get the key and value parts
                            key_value = match.group(0)
                            colon_pos = key_value.find(':')
                            if colon_pos == -1:
                                return key_value
                            
                            # Split into key and value
                            key = key_value[:colon_pos].strip()
                            value = key_value[colon_pos+1:].strip()
                            
                            # If value starts and ends with quotes, process it
                            if value.startswith('"') and value.endswith('",'):
                                # Remove start/end quotes
                                value = value[1:-2]
                                # Escape any unescaped quotes
                                value = value.replace('"', '\\"')
                                # Rebuild the key-value pair
                                return f'{key}: "{value}",'
                            elif value.startswith('"') and value.endswith('"'):
                                # Same as above but for last item without comma
                                value = value[1:-1]
                                value = value.replace('"', '\\"')
                                return f'{key}: "{value}"'
                            
                            return key_value
                        
                        # Use regex to find and fix all key-value pairs
                        pattern = r'"[^"]+"\s*:\s*"[^"]*(?:"{2,})[^"]*"(?:,)?'
                        fixed_content = re.sub(pattern, fix_json_string, content)
                        
                        try:
                            # Try to parse the fixed JSON
                            data = json.loads(fixed_content)
                            content = fixed_content
                            print("Successfully fixed and parsed JSON")
                        except json.JSONDecodeError as e:
                            print(f"Failed to fix JSON: {str(e)}")
                            # If we can't fix it, write the original content
                            pass
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
            print(f"✓ Saved file: {output_path} ({os.path.getsize(output_path)} bytes)")
            return {"data": {"attributes": {"status": "completed"}}}
            
        return response.text
        
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error {e.response.status_code}")
        if e.response.status_code != 200:
            print(f"Response: {e.response.text}")
        raise
    except Exception as e:
        print(f"Error: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        raise


def main():
    # Create argument parser
    parser = argparse.ArgumentParser(description="Transifex Translation CLI Tool")

    # Add commands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch strings from Transifex")
    fetch_parser.add_argument(
        "--mode",
        choices=["untranslated", "unreviewed", "all"],
        default="untranslated",
        help="Type of strings to fetch",
    )
    fetch_parser.add_argument(
        "--force", action="store_true", help="Force download even if cache exists"
    )
    fetch_parser.add_argument(
        "--async", action="store_true", help="Use async download to fetch files"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate translation files"
    )
    validate_parser.add_argument(
        "--directory",
        default="translations",
        help="Directory containing translation files to validate",
    )
    validate_parser.add_argument(
        "--format",
        choices=["all", "po", "json", "yaml"],
        default="all",
        help="File format to validate",
    )
    validate_parser.add_argument(
        "--skip-django",
        action="store_true",
        help="Skip Django's compilemessages validation for PO files",
    )
    validate_parser.add_argument(
        "--keep-mo",
        action="store_true",
        help="Keep generated .mo files after validation (by default they are removed)",
    )

    # Translate command
    translate_parser = subparsers.add_parser("translate", help="Translate strings")
    translate_parser.add_argument(
        "--update", action="store_true", help="Update translations in Transifex"
    )
    translate_parser.add_argument(
        "--mode",
        choices=["untranslated", "unreviewed"],
        default="untranslated",
        help="Type of strings to translate",
    )
    translate_parser.add_argument(
        "--force", action="store_true", help="Force download even if cache exists"
    )

    # Add update command
    update_parser = subparsers.add_parser(
        "update", help="Update Transifex from saved translations"
    )

    # Add review command
    review_parser = subparsers.add_parser("review", help="Review unreviewed translations using LLM")
    review_parser.add_argument(
        "--language", help="Language code to review. If not specified, reviews all languages with unreviewed strings"
    )
    review_parser.add_argument(
        "--update", action="store_true", help="Update approved translations in Transifex"
    )
    review_parser.add_argument(
        "--force", action="store_true", help="Force fetch new unreviewed strings before review"
    )
    review_parser.add_argument(
        "--approve-all", action="store_true", help="Automatically approve all updates without asking"
    )
    review_parser.add_argument(
        "--workers", type=int, default=4, help="Number of worker threads for parallel processing"
    )

    # Parse arguments
    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config()

        # Initialize API client
        api = TransifexAPI(
            config["api_token"], config["organization"], config["project"]
        )

        # Get all resources
        resources = api.get_project_resources()
        print(f"\nFound {len(resources)} resources")

        if args.command == "fetch":
            if getattr(args, 'async', False):
                # Use async download
                completed_jobs = fetch_strings_async(
                    api, resources, config, args.mode, args.force
                )
            else:
                # Use existing synchronous download
                strings_by_lang = fetch_strings(
                    api, resources, config, args.mode, args.force
                )
                for lang in strings_by_lang:
                    if args.force:  # Only save if we forced a new download
                        save_to_csv(strings_by_lang, lang, args.mode)
                    print(f"\nSaved {args.mode} strings for {lang} to CSV")

        elif args.command == "validate":
            if not os.path.exists(args.directory):
                print(f"Error: Directory {args.directory} does not exist")
                return

            validator = ValidationHandler()
            
            # Filter files based on format if specified
            if args.format != "all":
                def format_filter(file):
                    if args.format == "po":
                        return file.endswith(".po")
                    elif args.format == "json":
                        return file.endswith(".json")
                    elif args.format == "yaml":
                        return file.endswith((".yaml", ".yml"))
                    return True
            else:
                format_filter = lambda f: f.endswith((".po", ".json", ".yaml", ".yml"))

            # Walk through the directory and validate files
            print(f"\nValidating translation files in {args.directory}")
            print(f"Format filter: {args.format}")
            print(f"Django validation: {'disabled' if args.skip_django else 'enabled'}")
            print(f"MO files: {'kept' if args.keep_mo else 'removed after validation'}")
            
            results = validator.validate_directory(args.directory)
            validator.print_validation_report()

            # Exit with error if any invalid files found
            if results['invalid_files']:
                exit(1)

        elif args.command == "translate":
            # Create a map of resource names to IDs
            resources_map = {r["attributes"]["name"]: r["id"] for r in resources}
            # Fetch, translate, and optionally update strings
            strings_by_lang = fetch_strings(
                api, resources, config, args.mode, args.force
            )
            translate_strings(
                api, strings_by_lang, resources_map, args.mode, args.update
            )
            # Save original strings to CSV for reference
            for lang in strings_by_lang:
                if args.force:  # Only save if we forced a new download
                    save_to_csv(strings_by_lang, lang, args.mode)

        elif args.command == "update":
            # Create a map of resource names to IDs
            resources_map = {r["attributes"]["name"]: r["id"] for r in resources}
            # Update translations from saved files
            update_translations_from_files(api, resources_map)

        elif args.command == "review":
            # Create a map of resource names to IDs for Transifex updates
            resources_map = {r["attributes"]["name"]: r["id"] for r in resources}
            
            if args.update:
                # If update flag is set, look for approved CSV files to process
                approved_files = []
                if args.language:
                    approved_file = os.path.join("reviews", f"approved_{args.language}.csv")
                    if os.path.exists(approved_file):
                        approved_files.append((args.language, approved_file))
                    else:
                        print(f"No approved translations found for {args.language}")
                        return
                else:
                    # Look for all approved_*.csv files
                    if os.path.exists("reviews"):
                        for file in os.listdir("reviews"):
                            if file.startswith("approved_") and file.endswith(".csv"):
                                lang = file.replace("approved_", "").replace(".csv", "")
                                approved_files.append((lang, os.path.join("reviews", file)))
                
                if not approved_files:
                    print("No approved translations found to update.")
                    return

                # Process each approved file
                for lang, approved_file in approved_files:
                    print(f"\nProcessing approved translations for {lang} from {approved_file}")
                    with open(approved_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            resource_id = resources_map.get(row['Resource'])
                            if not resource_id:
                                print(f"! Resource not found for: {row['Resource']}")
                                continue

                            print(f"\nReview translation for: {row['String Key']}")
                            print(f"Source: {row['Source String']}")
                            print(f"Translation: {row['Translation']}")
                            print(f"Explanation: {row['Explanation']}")
                            
                            if not args.approve_all:
                                response = input("Mark as reviewed in Transifex? [y/N]: ").lower()
                                if response != 'y':
                                    print("Skipped.")
                                    continue

                            # Mark as reviewed in Transifex
                            api.review_translation(
                                resource_id,
                                lang,
                                row['String Key']
                            )
                            print(f"✓ Marked as reviewed in Transifex: {row['String Key']}")
                    
                    print(f"Finished processing {approved_file}")
                return

            # If not updating, proceed with review process
            languages_to_review = []
            if args.language:
                languages_to_review = [args.language]
            else:
                # Look for unreviewed_*.csv files in output directory
                if os.path.exists("output"):
                    for file in os.listdir("output"):
                        if file.startswith("unreviewed_") and file.endswith(".csv"):
                            lang = file.replace("unreviewed_", "").replace(".csv", "")
                            languages_to_review.append(lang)
            
            if not languages_to_review:
                print("No languages found for review. Please fetch unreviewed strings first or specify a language.")
                return

            for lang in languages_to_review:
                input_csv = os.path.join("output", f"unreviewed_{lang}.csv")
                
                # Fetch new strings if forced or if CSV doesn't exist
                if args.force or not os.path.exists(input_csv):
                    print(f"\nFetching unreviewed strings for {lang}...")
                    strings_by_lang = fetch_strings(
                        api, resources, {"target_languages": [lang]}, "unreviewed", True
                    )
                    if not strings_by_lang.get(lang):
                        print(f"No unreviewed strings found for {lang}")
                        continue

                print(f"\nReviewing translations for {lang}")
                reviewer = ReviewHandler(lang)
                approved_file, rejected_file, _ = reviewer.process_reviews(
                    input_csv, max_workers=args.workers
                )

        else:
            parser.print_help()

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
