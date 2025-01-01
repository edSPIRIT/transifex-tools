from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import json
import re
import os

class TranslationHandler:
    def __init__(self, target_language):
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-4o-mini")
        self.target_language = target_language
        
        # Define placeholder patterns for different template types
        self.placeholder_patterns = [
            (r'\{[^}]+\}', 'json'),           # JSON/React style: {name}
            (r'%\{[^}]+\}', 'ruby'),          # Ruby style: %{name}
            (r'<%[^%>]+%>', 'mako'),          # Mako style: <% name %>
            (r'\$\{[^}]+\}', 'shell'),        # Shell/JS style: ${name}
            (r'%\([^)]+\)s', 'python'),       # Python style: %(name)s
            (r'%[sdfi]', 'c-style'),          # C-style: %s, %d
            (r'\{\{[^}]+\}\}', 'handlebars')  # Handlebars style: {{name}}
        ]
        
        # Create a prompt template for translation
        self.translation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional translator. Translate the following text to {language}. 
                      Maintain the original meaning and context. 
                      IMPORTANT: The text contains special placeholders that must remain EXACTLY as they are.
                      These placeholders will be marked with __PLACEHOLDER_X__ tokens.
                      Do not translate or modify these tokens in any way."""),
            ("user", "Text to translate: {text}\nContext: {context}")
        ])
        
        # Prompt for review
        self.review_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional translator reviewing translations.
                      Compare the source text and its translation to {language}.
                      Check for:
                      1. Accuracy of meaning
                      2. Preservation of placeholders
                      3. Cultural appropriateness
                      4. Grammar and spelling
                      
                      Respond with only "APPROVE" or "REJECT" followed by a brief reason."""),
            ("user", """Source: {text}
                       Translation: {translation}
                       Context: {context}""")
        ])
        
    def _escape_placeholders(self, text):
        """Escape any potential placeholders in the text"""
        escaped_text = text
        placeholders = []
        
        # Find all types of placeholders
        for pattern, style in self.placeholder_patterns:
            matches = re.finditer(pattern, escaped_text)
            for match in matches:
                placeholder = match.group(0)
                token = f"__PLACEHOLDER_{len(placeholders)}__"
                placeholders.append({
                    'original': placeholder,
                    'style': style,
                    'token': token
                })
                escaped_text = escaped_text.replace(placeholder, token)
        
        return escaped_text, placeholders
        
    def _restore_placeholders(self, text, placeholders):
        """Restore placeholders in the translated text"""
        restored_text = text
        
        # Sort placeholders by token number to replace in correct order
        placeholders.sort(key=lambda x: int(re.search(r'\d+', x['token']).group()))
        
        for placeholder in placeholders:
            restored_text = restored_text.replace(
                placeholder['token'],
                placeholder['original']
            )
            
        return restored_text

    def translate_string(self, text, context=None):
        """Translate a single string using the LLM"""
        try:
            # Escape placeholders before translation
            escaped_text, placeholders = self._escape_placeholders(text)
            
            # Add placeholder info to context if any exist
            if placeholders:
                placeholder_info = "\nPlaceholders found: " + ", ".join(
                    f"{p['token']} ({p['style']} style)" for p in placeholders
                )
                context = (context or "") + placeholder_info
            
            # Create the chain and translate
            chain = self.translation_prompt | self.llm
            response = chain.invoke({
                "language": self.target_language,
                "text": escaped_text,
                "context": context or "No specific context provided"
            })
            
            # Restore placeholders in the translation
            translated_text = self._restore_placeholders(response.content, placeholders)
            
            # Verify all placeholders were preserved
            for placeholder in placeholders:
                if placeholder['original'] not in translated_text:
                    print(f"Warning: Placeholder {placeholder['original']} was lost in translation")
                    return text  # Return original if any placeholder was lost
                    
            return translated_text
            
        except Exception as e:
            print(f"Error translating text: {text}")
            print(f"Error details: {str(e)}")
            return text
            
    def review_translation(self, source_text, translation, context=None):
        """Review a translation and return if it should be approved"""
        chain = self.review_prompt | self.llm
        
        try:
            response = chain.invoke({
                "language": self.target_language,
                "text": source_text,
                "translation": translation,
                "context": context or "No specific context provided"
            })
            return response.content.startswith("APPROVE")
        except Exception as e:
            print(f"Error reviewing translation: {source_text}")
            print(f"Error details: {str(e)}")
            return False
    
    def process_strings(self, strings, mode='untranslated'):
        """Process strings based on mode"""
        results = []
        for string_info in strings:
            if mode == 'untranslated':
                # For untranslated strings, generate new translation
                translation = self.translate_string(
                    string_info['source'],
                    string_info.get('context', '')
                )
                results.append({
                    'key': string_info['key'],
                    'source': string_info['source'],
                    'translation': translation,
                    'context': string_info.get('context', ''),
                    'action': 'translate'
                })
            else:  # unreviewed
                # For unreviewed strings, only review the existing translation
                approved = self.review_translation(
                    string_info['source'],
                    string_info['attributes']['strings']['other'],  # Get existing translation
                    string_info.get('context', '')
                )
                results.append({
                    'key': string_info['key'],
                    'source': string_info['source'],
                    'translation': string_info['attributes']['strings']['other'],  # Keep existing translation
                    'context': string_info.get('context', ''),
                    'action': 'review',
                    'approved': approved
                })
        return results

def save_translations(translations, language, resource_name, output_dir='translations'):
    """Save translations to a single JSON file per language"""
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filename based on language only
    filename = os.path.join(output_dir, f"{language}.json")
    
    # Load existing translations if file exists
    existing_translations = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                existing_translations = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not read existing translations from {filename}")
    
    # Add or update translations for this resource
    if resource_name not in existing_translations:
        existing_translations[resource_name] = []
    existing_translations[resource_name].extend(translations)
    
    # Save updated translations
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(existing_translations, f, ensure_ascii=False, indent=2)
    
    print(f"Updated translations for {resource_name} in {filename}")
    return filename 