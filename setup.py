from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="sunny_narrator",
    version="0.1.0",
    author="N15D",
    author_email="n@uwns.org",
    description="AI book translator for xml, fb2, txt ",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/neowisard/sunny_narrator",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        "xml.etree.ElementTree",
        "icecream",
        "python-dotenv",
        "pathlib",
        "openai",
        "tiktoken",
        "langchain-text-splitters",
    ],
    entry_points={
        'console_scripts': [
            'your_script_name=app:main',  # Если у вас есть главный скрипт, который нужно запускать
        ],
    },
)