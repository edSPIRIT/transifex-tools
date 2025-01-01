import os
import json
import yaml
import polib
import subprocess
import glob
import shutil
import tempfile
from typing import Dict, List, Tuple, Optional

class ValidationHandler:
    def __init__(self):
        self.validation_results = {
            'valid_files': [],
            'invalid_files': [],
            'errors': []
        }
        self.mo_files_created = []
        self.temp_dirs = []

    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a translation file based on its extension.
        Returns a tuple of (is_valid, error_message).
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        try:
            if ext == '.po':
                return self._validate_po_file(file_path)
            elif ext == '.json':
                return self._validate_json_file(file_path)
            elif ext == '.yaml' or ext == '.yml':
                return self._validate_yaml_file(file_path)
            else:
                return False, f"Unsupported file format: {ext}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _validate_po_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a PO file:
        - Check if it can be parsed
        - Verify that all translations are properly formatted
        - Check for missing placeholders in translations
        - Run Django's compilemessages validation
        """
        try:
            # Basic polib validation
            po = polib.pofile(file_path)
            
            # Check for basic parsing
            if not po:
                return False, "Failed to parse PO file"

            errors = []
            
            for entry in po:
                # Skip untranslated entries
                if not entry.msgstr:
                    continue

                # Check for placeholder consistency
                source_placeholders = self._extract_placeholders(entry.msgid)
                translation_placeholders = self._extract_placeholders(entry.msgstr)

                missing_placeholders = source_placeholders - translation_placeholders
                extra_placeholders = translation_placeholders - source_placeholders

                if missing_placeholders or extra_placeholders:
                    error_parts = []
                    error_parts.append(f"Line {entry.linenum}:")
                    error_parts.append(f"Source: {entry.msgid}")
                    error_parts.append(f"Translation: {entry.msgstr}")
                    
                    if missing_placeholders:
                        error_parts.append(f"Missing placeholders: {missing_placeholders}")
                    if extra_placeholders:
                        error_parts.append(f"Extra placeholders: {extra_placeholders}")
                    
                    errors.append("\n   ".join(error_parts))

            # Django validation using compilemessages
            django_error = self._validate_with_django(file_path)
            if django_error:
                errors.append(django_error)

            if errors:
                return False, "\n\n".join(errors)
            return True, None

        except Exception as e:
            return False, f"PO file validation error: {str(e)}"

    def _validate_with_django(self, file_path: str) -> Optional[str]:
        """
        Validate PO file using Django's compilemessages command.
        Returns error message if validation fails, None if successful.
        """
        try:
            # Create a temporary Django project structure
            temp_dir = tempfile.mkdtemp()
            self.temp_dirs.append(temp_dir)
            
            # Create Django project structure
            project_dir = os.path.join(temp_dir, 'django_project')
            locale_dir = os.path.join(project_dir, 'locale')
            os.makedirs(project_dir)
            
            # Copy Django settings
            settings_dir = os.path.join(project_dir, 'settings')
            os.makedirs(settings_dir)
            with open(os.path.join(settings_dir, '__init__.py'), 'w') as f:
                f.write('')
            settings_path = os.path.join(os.path.dirname(__file__), 'django_settings.py')
            shutil.copy2(settings_path, os.path.join(settings_dir, 'settings.py'))
            
            # Copy PO file to Django locale structure
            po_locale_dir = os.path.dirname(os.path.dirname(file_path))
            lang_code = os.path.basename(po_locale_dir)
            target_dir = os.path.join(locale_dir, lang_code, 'LC_MESSAGES')
            os.makedirs(target_dir)
            temp_po_path = os.path.join(target_dir, 'django.po')
            shutil.copy2(file_path, temp_po_path)
            
            # Run Django's compilemessages
            result = subprocess.run(
                ['django-admin', 'compilemessages', '-l', lang_code],
                cwd=project_dir,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    'DJANGO_SETTINGS_MODULE': 'settings.settings',
                    'PYTHONPATH': project_dir
                }
            )

            if result.returncode != 0:
                # Parse the error message to get line numbers
                error_msg = result.stderr
                error_lines = []
                
                # Extract line numbers from error messages
                import re
                line_numbers = re.findall(r'django\.po:(\d+):', error_msg)
                
                if line_numbers:
                    # Read the original PO file
                    po = polib.pofile(file_path)
                    
                    # Add context for each error
                    for line_num in line_numbers:
                        line_num = int(line_num)
                        # Find the entry containing this line
                        for entry in po:
                            if entry.linenum <= line_num and (entry.linenum + len(str(entry).split('\n'))) >= line_num:
                                error_lines.append(f"\nError at line {line_num}:")
                                error_lines.append(f"msgid: {entry.msgid}")
                                if hasattr(entry, 'msgid_plural') and entry.msgid_plural:
                                    error_lines.append(f"msgid_plural: {entry.msgid_plural}")
                                if isinstance(entry.msgstr, list):
                                    for i, msg in enumerate(entry.msgstr):
                                        error_lines.append(f"msgstr[{i}]: {msg}")
                                else:
                                    error_lines.append(f"msgstr: {entry.msgstr}")
                                break
                    
                    # Combine original error with context
                    error_msg = error_msg + "\n\nDetailed context:" + "\n".join(error_lines)
                
                return f"Django validation error:\n{error_msg}"

            # Track any MO files that were created in the original location
            mo_path = file_path.replace('.po', '.mo')
            if os.path.exists(mo_path):
                self.mo_files_created.append(mo_path)

            return None

        except subprocess.SubprocessError as e:
            return f"Django validation failed: {str(e)}"
        except Exception as e:
            return f"Django validation error: {str(e)}"
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_dir)
                self.temp_dirs.remove(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to clean up temporary directory {temp_dir}: {e}")

    def cleanup_mo_files(self):
        """
        Clean up any MO files that were created during validation.
        """
        # Clean up MO files
        for mo_file in self.mo_files_created:
            try:
                if os.path.exists(mo_file):
                    os.remove(mo_file)
                    print(f"Cleaned up MO file: {mo_file}")
            except Exception as e:
                print(f"Failed to remove MO file {mo_file}: {e}")

        self.mo_files_created = []

        # Clean up any remaining temporary directories
        for temp_dir in self.temp_dirs[:]:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    self.temp_dirs.remove(temp_dir)
            except Exception as e:
                print(f"Failed to remove temporary directory {temp_dir}: {e}")

    def _validate_json_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a JSON translation file:
        - Check if it's valid JSON
        - Verify the structure matches expected format
        - Check for missing translations and placeholders
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return False, "JSON must contain a dictionary of translations"

            errors = []
            
            def check_translations(obj, path="", source_lang=None):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        
                        # If we have both source and translation
                        if isinstance(value, dict) and 'source' in value and 'translation' in value:
                            source_placeholders = self._extract_placeholders(value['source'])
                            translation_placeholders = self._extract_placeholders(value['translation'])
                            
                            missing_placeholders = source_placeholders - translation_placeholders
                            extra_placeholders = translation_placeholders - source_placeholders
                            
                            if missing_placeholders or extra_placeholders:
                                error_parts = []
                                error_parts.append(f"Key: {new_path}")
                                error_parts.append(f"Source: {value['source']}")
                                error_parts.append(f"Translation: {value['translation']}")
                                
                                if missing_placeholders:
                                    error_parts.append(f"Missing placeholders: {missing_placeholders}")
                                if extra_placeholders:
                                    error_parts.append(f"Extra placeholders: {extra_placeholders}")
                                
                                errors.append("\n   ".join(error_parts))
                        
                        elif isinstance(value, (dict, str)):
                            check_translations(value, new_path)
                        else:
                            errors.append(f"Invalid value type at {new_path}: {type(value)}")

            check_translations(data)

            if errors:
                return False, "\n\n".join(errors)
            return True, None

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}"
        except Exception as e:
            return False, f"JSON validation error: {str(e)}"

    def _validate_yaml_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a YAML translation file:
        - Check if it's valid YAML
        - Verify the structure matches expected format
        - Check for missing translations and placeholders
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                return False, "YAML must contain a dictionary of translations"

            errors = []
            
            def check_translations(obj, path="", source_lang=None):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        
                        # If we have both source and translation
                        if isinstance(value, dict) and 'source' in value and 'translation' in value:
                            source_placeholders = self._extract_placeholders(value['source'])
                            translation_placeholders = self._extract_placeholders(value['translation'])
                            
                            missing_placeholders = source_placeholders - translation_placeholders
                            extra_placeholders = translation_placeholders - source_placeholders
                            
                            if missing_placeholders or extra_placeholders:
                                error_parts = []
                                error_parts.append(f"Key: {new_path}")
                                error_parts.append(f"Source: {value['source']}")
                                error_parts.append(f"Translation: {value['translation']}")
                                
                                if missing_placeholders:
                                    error_parts.append(f"Missing placeholders: {missing_placeholders}")
                                if extra_placeholders:
                                    error_parts.append(f"Extra placeholders: {extra_placeholders}")
                                
                                errors.append("\n   ".join(error_parts))
                        
                        elif isinstance(value, (dict, str)):
                            check_translations(value, new_path)
                        else:
                            errors.append(f"Invalid value type at {new_path}: {type(value)}")

            check_translations(data)

            if errors:
                return False, "\n\n".join(errors)
            return True, None

        except yaml.YAMLError as e:
            return False, f"Invalid YAML format: {str(e)}"
        except Exception as e:
            return False, f"YAML validation error: {str(e)}"

    def _extract_placeholders(self, text: str) -> set:
        """
        Extract placeholders from a string. Handles both Python format strings
        and Django template variables.
        """
        import re
        placeholders = set()
        
        # Python format strings like %(name)s or {name}
        python_formats = re.findall(r'%\([^)]+\)[sd]|\{[^}]+\}', text)
        placeholders.update(python_formats)
        
        # Django template variables like {{ variable }}
        django_vars = re.findall(r'\{\{[^}]+\}\}', text)
        placeholders.update(django_vars)
        
        return placeholders

    def validate_directory(self, directory: str) -> Dict:
        """
        Validate all translation files in a directory and its subdirectories.
        Returns a dictionary with validation results.
        """
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    if file.endswith(('.po', '.json', '.yaml', '.yml')):
                        file_path = os.path.join(root, file)
                        is_valid, error = self.validate_file(file_path)
                        
                        if is_valid:
                            self.validation_results['valid_files'].append(file_path)
                        else:
                            self.validation_results['invalid_files'].append(file_path)
                            self.validation_results['errors'].append({
                                'file': file_path,
                                'error': error
                            })

            return self.validation_results
        finally:
            # Clean up any MO files that were created during validation
            self.cleanup_mo_files()

    def print_validation_report(self):
        """Print a formatted validation report."""
        print("\n=== Validation Report ===")
        print(f"\nValid files ({len(self.validation_results['valid_files'])}):")
        for file in self.validation_results['valid_files']:
            print(f"✓ {file}")

        if self.validation_results['invalid_files']:
            print(f"\nInvalid files ({len(self.validation_results['invalid_files'])}):")
            for error in self.validation_results['errors']:
                print(f"\n❌ {error['file']}")
                print(f"   {error['error']}") 