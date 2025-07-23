# text_splitter.py
import re


class TextSplitter:
    @staticmethod
    def smart_split(text, max_length=2000):
        text = re.sub(r"\s+", " ", text.strip())
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > max_length:
                subs = re.split(r"(?<=[,;:])\s+", sentence)
                for part in subs:
                    if len(current) + len(part) + 2 <= max_length:
                        current += part + " "
                    else:
                        if current:
                            chunks.append(current.strip())
                        current = part + " "
            else:
                if len(current) + len(sentence) + 2 <= max_length:
                    current += sentence + " "
                else:
                    if current:
                        chunks.append(current.strip())
                    current = sentence + " "
        if current:
            chunks.append(current.strip())

        return chunks
