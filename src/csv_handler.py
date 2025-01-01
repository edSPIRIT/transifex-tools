import os
import csv

def save_to_csv(data, language, mode='untranslated', output_dir='output'):
    """Save strings to CSV files with mode-specific naming"""
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f'{mode}_{language}.csv')
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Define columns based on mode
        if mode == 'unreviewed':
            headers = ['Resource', 'String Key', 'Source String', 'Translation', 'Context']
        else:  # untranslated
            headers = ['Resource', 'String Key', 'Source String', 'Context']
            
        writer.writerow(headers)
        
        for resource_name, strings in data[language].items():
            for string_info in strings:
                row = [
                    resource_name,
                    string_info['key'],
                    string_info['source'],
                ]
                
                if mode == 'unreviewed':
                    # Make sure we have the translation for unreviewed strings
                    translation = string_info.get('translation', '')
                    if not translation:
                        print(f"Warning: No translation found for key: {string_info['key']}")
                    row.append(translation)
                    
                row.append(string_info.get('context', ''))
                writer.writerow(row)
                
                # Debug output
                if mode == 'unreviewed':
                    print(f"Debug - Saving to CSV:")
                    print(f"Key: {string_info['key']}")
                    print(f"Source: {string_info['source']}")
                    print(f"Translation: {string_info.get('translation', '')}")
    
    print(f"Saved {len(data[language])} resources to {filename}") 