from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="sunny_narrator",
    version="0.1.0",
    author="nick Kutuzov",
    author_email="kutuzovnick@gmail.com",
    description="AI book translator for xml, fb2, txt",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/neowisard/sunny_narrator",
    # Assuming code is in 'src' directory and we want to package it.
    packages=find_packages(where="src"), 
    package_dir={"": "src"},
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
        "pydantic>=2.11.7",
        "spacy",
        "beautifulsoup4",
        "scikit-learn",
        "lxml",
        "joblib",
        "thinc",
        "spacy-transformers",
        "EbookLib",
        "more-itertools",
        # Note: 'torch' and 'cupy' often require specific versions or index URLs for GPU support.
        # We include generic names here.
        "torch", 
        "cupy" 
    ],
    entry_points={
        'console_scripts': [
            # Assuming 'app.py' defines a main function, but usually entry points point to modules inside packages.
            # Since app.py is top-level, it's hard to reference via entry_points if not installed as a module.
            # If the logic is moved to src/main.py, we could use:
            # 'sunny-narrator=main:main', 
        ],
    },
)