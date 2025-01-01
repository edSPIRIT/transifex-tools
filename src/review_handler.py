import csv
import os
from typing import Dict, List, Tuple
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading


class ReviewHandler:
    def __init__(self, language: str):
        self.language = language
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-4o-mini")
        
        # Thread-safe queues for collecting results
        self.approved_queue = Queue()
        self.rejected_queue = Queue()
        
        # Create a prompt template for review
        self.review_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a professional translator reviewing translations.
                      Compare the source text and its translation to {language}.
                      Check for:
                      1. Accuracy of meaning
                      2. Preservation of placeholders
                      3. Cultural appropriateness
                      4. Grammar and spelling
                      
                      Respond with:
                      VERDICT: [APPROVE/REJECT]
                      REASON: [Brief explanation]""",
                ),
                (
                    "user",
                    """Source: {source}
                       Translation: {translation}
                       Context: {context}""",
                ),
            ]
        )

    def read_unreviewed_strings(self, csv_path: str) -> List[Dict]:
        """Read unreviewed strings from CSV file"""
        unreviewed_strings = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unreviewed_strings.append(row)
        return unreviewed_strings

    def review_translation(self, item: Dict) -> Dict:
        """
        Use LLM to review a translation
        Returns the item with review results added
        """
        try:
            chain = self.review_prompt | self.llm
            response = chain.invoke(
                {
                    "language": self.language,
                    "source": item["Source String"],
                    "translation": item["Translation"],
                    "context": item.get("Context", "No specific context provided"),
                }
            )

            # Parse the response
            content = response.content
            verdict_line = next(
                line for line in content.split("\n") if line.startswith("VERDICT:")
            )
            reason_line = next(
                line for line in content.split("\n") if line.startswith("REASON:")
            )

            is_valid = "APPROVE" in verdict_line
            explanation = reason_line.replace("REASON:", "").strip()

            result = {
                "resource": item["Resource"],
                "key": item["String Key"],
                "source": item["Source String"],
                "translation": item["Translation"],
                "context": item.get("Context", ""),
                "is_valid": is_valid,
                "explanation": explanation,
            }

            # Add to appropriate queue
            if is_valid:
                self.approved_queue.put(result)
            else:
                self.rejected_queue.put(result)

            return result

        except Exception as e:
            print(f"Error reviewing translation: {str(e)}")
            error_result = {**item, "is_valid": False, "explanation": f"Error during review: {str(e)}"}
            self.rejected_queue.put(error_result)
            return error_result

    def save_results_to_csv(self, results: List[Dict], filename: str):
        """Save results to a CSV file"""
        if not results:
            return

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Resource",
                    "String Key",
                    "Source String",
                    "Translation",
                    "Context",
                    "Is Valid",
                    "Explanation",
                ]
            )

            for result in results:
                writer.writerow(
                    [
                        result["resource"],
                        result["key"],
                        result["source"],
                        result["translation"],
                        result["context"],
                        result["is_valid"],
                        result["explanation"],
                    ]
                )

    def process_reviews(self, input_csv: str, output_dir: str = "reviews", max_workers: int = 4) -> Tuple[str, str, List[Dict]]:
        """Process all translations in parallel and generate review reports"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        unreviewed_strings = self.read_unreviewed_strings(input_csv)
        all_results = []
        approved_results = []
        rejected_results = []

        print(f"\nReviewing {len(unreviewed_strings)} translations using {max_workers} workers...")

        # Process translations in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(self.review_translation, item): item 
                for item in unreviewed_strings
            }
            
            for future in as_completed(future_to_item):
                result = future.result()
                all_results.append(result)
                
                # Print result immediately
                status = "✅ APPROVED" if result["is_valid"] else "❌ REJECTED"
                print(f"\n{status}: {result['key']}")
                print(f"Source: {result['source']}")
                print(f"Translation: {result['translation']}")
                print(f"Reason: {result['explanation']}")

        # Collect results from queues
        while not self.approved_queue.empty():
            approved_results.append(self.approved_queue.get())
        while not self.rejected_queue.empty():
            rejected_results.append(self.rejected_queue.get())

        # Save results to separate files
        approved_file = os.path.join(output_dir, f"approved_{self.language}.csv")
        rejected_file = os.path.join(output_dir, f"rejected_{self.language}.csv")
        
        self.save_results_to_csv(approved_results, approved_file)
        self.save_results_to_csv(rejected_results, rejected_file)

        print(f"\nReview Summary:")
        print(f"Total strings reviewed: {len(all_results)}")
        print(f"Approved: {len(approved_results)}")
        print(f"Rejected: {len(rejected_results)}")
        print(f"\nApproved translations saved to: {approved_file}")
        print(f"Rejected translations saved to: {rejected_file}")

        return approved_file, rejected_file, approved_results
