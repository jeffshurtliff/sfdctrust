# -*- coding: utf-8 -*-
"""
:Module:            tools.ci.matrix
:Synopsis:          Derive CI runtimes from the advertised Python classifiers
:Created By:        Jeff Shurtliff
:Last Modified:     Jeff Shurtliff (via GPT-6.1 Sol)
:Modified Date:     13 Nov 2026
"""

import json
import re
import tomllib
from pathlib import Path


def matrix(project: dict) -> dict:
    versions = sorted(
        {
            match.group(1)
            for classifier in project['classifiers']
            if (match := re.fullmatch(r'Programming Language :: Python :: (3\.\d+)', classifier))
        },
        key=lambda value: tuple(map(int, value.split('.'))),
    )
    if not versions or project['requires-python'] != f'>={versions[0]}':
        raise ValueError('Review the CI policy when changing the supported Python range.')
    return {
        'include': [
            {'os': 'macos-latest', 'python': versions[0]},
            {'os': 'windows-latest', 'python': versions[0]},
            *[{'os': 'ubuntu-latest', 'python': value} for value in versions],
        ]
    }


if __name__ == '__main__':
    print(json.dumps(matrix(tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project'])))
