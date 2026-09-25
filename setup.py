from setuptools import setup, find_packages

setup(
    name="postcast",
    version="0.2.4",
    description="A GTK4 podcast player for postmarketOS",
    packages=find_packages(include=["postcast", "postcast.*"]),
    package_data={"postcast": ["data/*"]},
    include_package_data=True,
    entry_points={"gui_scripts": ["postcast=postcast.__main__:main"]},
    python_requires=">=3.9",
)
