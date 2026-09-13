from transformers import CLIPModel, CLIPProcessor
MODEL = "openai/clip-vit-base-patch32"
REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
if __name__ == "__main__":
    CLIPModel.from_pretrained(MODEL, revision=REVISION)
    CLIPProcessor.from_pretrained(MODEL, revision=REVISION)
