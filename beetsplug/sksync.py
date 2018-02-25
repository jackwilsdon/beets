# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2018, ???.
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

"""Update tracked artists on SongKick.
"""
from __future__ import division, absolute_import, print_function

from beets.plugins import BeetsPlugin
from beets import autotag, library, ui, util
from beets.autotag import hooks
from collections import defaultdict
import requests


class SKSyncPlugin(BeetsPlugin):

    # Official SongKick API
    api_url = "https://api.songkick.com/api/3.0"
    search_endpoint = "search/artists.json?api_key={api_key}&query={query}"
    tracking_endpoint = "users/{username}/artists/tracked.json?apikey={api_key}&page={page}"

    # Unofficial SongKick API
    site_url = "https://www.songkick.com"
    artist_endpoint = "artists/{id}"
    track_endpoint = "trackings"
    untrack_endpoint = "trackings/untrack"

    def __init__(self):
        super(SKSyncPlugin, self).__init__()

        self.config.add({
            'api_key': None,
            'username': None
        })

    def commands(self):
        cmd = ui.Subcommand('sksync',
                            help=u'update SongKick tracks')
        cmd.parser.add_option(
            u'-p', u'--pretend', action='store_true',
            help=u'show all changes but do nothing')
        cmd.parser.add_option(
            u'-n', u'--nountrack', action='store_true', dest='no_untrack',
            help=u"don't untrack artists on SongKick")
        cmd.func = self.func
        return [cmd]

    def func(self, lib, opts, args):
        """Handler for the sksync subcommand.
        """

        api_key = self.config["api_key"].get()
        username = self.config["username"].get()

        if api_key is None:
            raise ui.UserError("missing api_key")

        if username is None:
            raise ui.UserError("missing username")

        songkick_aritsts = self.get_songkick_artists(api_key, username)
        local_artists = self.get_artists(lib)
        new_artists = [ artist for artist in local_artists if artist not in songkick_aritsts ]

        ui.print_("Found {} new artist(s) to sync".format(len(new_artists)))

        for artist in new_artists:
            ui.print_(" - " + artist)

        if not ui.input_yn(u"Sync? (Y/n)"):
            return

    def get_artists(self, lib):
        return set(x.artist for x in lib.items())

    def get_songkick_artists(self, api_key, username):
        def get_page_artists(page):
            url = (self.api_url + "/" + self.tracking_endpoint).format(api_key=api_key, username=username, page=page)

            self._log.debug("making request for page {}: {}", page, url)

            response = requests.get(url).json()["resultsPage"]

            if response["status"] != "ok":
                raise ui.UserError("status not OK from API: {}".format(response["error"]["message"]))

            if "artist" not in response["results"]:
                self._log.debug("got 0 artists")
                return None

            self._log.debug("got {} artists", len(response["results"]["artist"]))

            return set(artist["displayName"] for artist in response["results"]["artist"])

        artists = []
        page = 1

        while True:
            page_artists = get_page_artists(page)

            if page_artists is None:
                break

            artists += page_artists
            page += 1

        self._log.debug("got {} artists over {} page(s)", len(artists), page - 1)

        return artists
