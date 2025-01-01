import os
import json
import yaml
import polib
from typing import Dict, List, Tuple, Optional

class ValidationHandler:
    def __init__(self):
        self.validation_results = {
            'valid_files': [],
            'invalid_files': [],
            'errors': []
        }

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
        """
        try:
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

            if errors:
                return False, "\n\n".join(errors)
            return True, None

        except Exception as e:
            return False, f"PO file validation error: {str(e)}"

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