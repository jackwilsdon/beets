# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2015, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Allows custom commands to be run when an event is emitted by beets"""
from __future__ import division, absolute_import, print_function

import string
import subprocess

from beets import ui
from beets.plugins import BeetsPlugin
from beets.util import shlex_split, arg_encoding
from logging import DEBUG, ERROR


class CodingFormatter(string.Formatter):
    """A variant of `string.Formatter` that converts everything to `unicode`
    strings.

    This is necessary on Python 2, where formatting otherwise occurs on
    bytestrings. It intercepts two points in the formatting process to decode
    the format string and all fields using the specified encoding. If decoding
    fails, the values are used as-is.
    """

    def __init__(self, coding):
        """Creates a new coding formatter with the provided coding."""
        self._coding = coding

    def format(self, format_string, *args, **kwargs):
        """Formats the provided string using the provided arguments and keyword
        arguments.

        This method decodes the format string using the formatter's coding.

        See str.format and string.Formatter.format.
        """
        if isinstance(format_string, bytes):
            format_string = format_string.decode(self._coding)

        return super(CodingFormatter, self).format(format_string, *args,
                                                   **kwargs)

    def convert_field(self, value, conversion):
        """Converts the provided value given a conversion type.

        This method decodes the converted value using the formatter's coding.

        See string.Formatter.convert_field.
        """
        converted = super(CodingFormatter, self).convert_field(value,
                                                               conversion)

        if isinstance(converted, bytes):
            return converted.decode(self._coding)

        return converted


class HookPlugin(BeetsPlugin):
    """Allows custom commands to be run when an event is emitted by beets"""
    def __init__(self):
        super(HookPlugin, self).__init__()

        self.config.add({
            'hooks': []
        })

        hooks = self.config['hooks'].get(list)

        for hook_index in range(len(hooks)):
            hook = self.config['hooks'][hook_index]

            hook_event = hook['event'].as_str()
            hook_command = hook['command'].as_str()
            hook_on_error = hook['on_error'].as_str() \
                if hook['on_error'].exists() else 'log'

            self.create_and_register_hook(hook_event, hook_command,
                                          hook_on_error)

    def handle_error(self, method, error):
        if method == 'abort':
            raise ui.UserError(error)
        else:
            self._log.log(ERROR if method == 'log' else DEBUG, error)

    def create_and_register_hook(self, event, command, on_error):
        def hook_function(**kwargs):
            if command is None or len(command) == 0:
                self._log.error(u'invalid command "{}" for event {}', command,
                                event)
                return

            if on_error not in ('abort', 'ignore', 'log'):
                self._log.error(u'invalid on_error "{}" for event {}',
                                on_error, event)
                return

            # Use a string formatter that works on Unicode strings.
            formatter = CodingFormatter(arg_encoding())

            command_pieces = shlex_split(command)

            for i, piece in enumerate(command_pieces):
                command_pieces[i] = formatter.format(piece, event=event,
                                                     **kwargs)

            self._log.debug(u'running command "{}" for event {}',
                            u' '.join(command_pieces), event)

            try:
                subprocess.check_call(command_pieces)
            except subprocess.CalledProcessError as exc:
                self.handle_error(on_error,
                                  u'hook for {} exited with status {}'
                                  .format(event, exc.returncode))
            except OSError as exc:
                self.handle_error(on_error,
                                  u'hook for {} failed: {}'.format(event, exc))

        self.register_listener(event, hook_function)
