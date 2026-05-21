import os
from google import genai
from google.genai import types

def test_image():
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    try:
        models = client.models.list()
        for m in models:
            if "image" in m.name.lower() or "imagen" in m.name.lower():
                print(m.name)
        
        result = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt='vintage 1970s executive office',
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="3:4"
            )
        )
        print("Success!", type(result))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_image()
