#!/bin/bash

# Paths
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
MODULE_DIR="$DIR/$(basename $DIR)"

BLACK=black
BLACK_OPTS="--line-length 79"
LINTER=$(which flake8)
GITIGNORE_URL="https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore"

# Update .gitignore if older than 30 days
GITIGNORE_PATH="$DIR/.gitignore"
if [ ! -f $GITIGNORE_PATH ] || [ `find $GITIGNORE_PATH -mtime +30` ]; then
    echo "📄  Updating .gitignore"
    wget -O $GITIGNORE_PATH $GITIGNORE_URL 2>/dev/null
fi

# Run black
echo "🖤  Running black"
$BLACK $BLACK_OPTS $MODULE_DIR/*.py

# Run linter
echo "🔍  Running linter"
if [ -n "$LINTER" ]; then
    $LINTER $MODULE_DIR/*.py
    if [ $? -ne 0 ]; then
        echo "❌  Linting failed"
        exit 1
    fi
    echo "✅  Linting passed"
else
    echo "⚠️  flake8 not found, skipping linting"
fi

# Run tests
echo "🧪  Running tests"
python3 -m unittest discover -s $MODULE_DIR
if [ $? -ne 0 ]; then
    echo "❌  Tests failed"
    exit 1
fi

# Clean up
echo "🧹  Cleaning up"
find . -type d -name '__pycache__' -exec rm -r {} +
find . -type d -name '*.egg-info' -exec rm -r {} +

echo "✅  Build successful"

# --------------------------------------------------------------------------- #
# Build & upload package                                                      #
# --------------------------------------------------------------------------- #
read -p "🚀  Build and upload package? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌  Build aborted"
    exit 1
fi

echo "📦  Building package"
python3 setup.py sdist bdist_wheel
if [ $? -ne 0 ]; then
    echo "❌  Build failed"
    exit 1
fi

echo "⬆️  Uploading package"
twine upload dist/*

echo "🎉  Build and upload successful"

exit 0
