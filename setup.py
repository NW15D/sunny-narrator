from setuptools import setup, find_packages
import os

# Create src/__init__.py if it doesn't exist
src_init = os.path.join(os.path.dirname(__file__), "src", "__init__.py")
if not os.path.exists(src_init):
    with open(src_init, "w") as f:
        pass

setup(
    name="sunny_narrator",
    version="0.1.0",
    author="nick Kutuzov",
    author_email="kutuzovnick@gmail.com",
    description="AI book translator for xml, fb2, txt",
    url="https://github.com/neowisard/sunny_narrator",
    packages=find_packages(), 
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    install_requires=[
        "icecream",
        "python-dotenv",
        "openai",
        "numpy",
        "tiktoken",
        "langchain-text-splitters",
        "pydantic>=2.0.0",
        "spacy",
        "beautifulsoup4",
        "scikit-learn",
        "torch",
        "lxml",
        "cupy-cuda12x",
        "more-itertools",
        "joblib",
        "thinc",
        "spacy-transformers",
        "EbookLib",
        "Pillow"
    ],
)