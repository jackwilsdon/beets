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
import urllib
from urllib.parse import urlencode, parse_qs, urlsplit, urlunsplit

def set_query_parameter(url, param_name, param_value):
    """Given a URL, set or replace a query parameter and return the
    modified URL.

    >>> set_query_parameter('http://example.com?foo=bar&biz=baz', 'foo', 'stuff')
    'http://example.com?foo=stuff&biz=baz'

    """
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = parse_qs(query_string)

    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)

    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


class SKSyncPlugin(BeetsPlugin):

    # Official SongKick API
    api_url = "https://api.songkick.com/api/3.0"
    search_endpoint = "search/artists.json?apikey={api_key}&query={query}"
    tracking_endpoint = "users/{username}/artists/tracked.json?apikey={api_key}"

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

        local_artists = self.get_library_artists(lib)
        songkick_artists = self.get_songkick_artists(api_key, username)

        # Fetch a list of local artists who aren't in the remote artist list.
        new_artists = dict((mbid, name) for mbid, name in local_artists.items() if mbid not in songkick_artists)

        ui.print_("Found {} new artist(s) to sync".format(len(new_artists)))

        # If there's no new artists then there's nothing to do.
        if len(new_artists) == 0:
            return

        for artist in new_artists.values():
            ui.print_(" - " + artist)

        if not ui.input_yn(u"Sync? (Y/n)"):
            return

        for mbid, artist in new_artists.items():
            self._log.debug("Searching for {}...", artist)

            results = self.search_songkick_artists(api_key, artist)


            print(results)
            print(mbid)

            if mbid not in results:
                self._log.debug("Couldn't find matching artist with MBID {}", mbid)
                continue

            print("Found match!")

    @staticmethod
    def get_library_artists(lib):
        return dict((x.mb_artistid, x.artist) for x in lib.items())

    def paginated_request(self, url, result_key):
        page = 1
        results = []

        while True:
            page_url = set_query_parameter(url, 'page', page)

            self._log.debug("making request for page {}: {}", page, page_url)

            # Every response should contain a results page.
            response = requests.get(page_url).json()["resultsPage"]

            # Every response should have a status attribute.
            if response["status"] != "ok":
                raise ui.UserError("status not OK from API: {}".format(response["error"]["message"]))

            # Stop if the key doesn't exist, as this usually means it's the last page.
            if result_key not in response["results"]:
                self._log.debug("got 0 {}s on page {}", result_key, page)
                break

            self._log.debug("got {} {}s on page {}", len(response["results"][result_key]), result_key, page)

            page += 1
            results += response["results"][result_key]

        self._log.debug("got {} {}s across {} page(s)", len(results), result_key, page)

        return results

    def get_songkick_artists(self, api_key, username):
        url = (self.api_url + "/" + self.tracking_endpoint).format(
            api_key=urllib.parse.quote_plus(api_key),
            username=urllib.parse.quote_plus(username))

        artists = {}

        for artist in self.paginated_request(url, "artist"):
            name = artist["displayName"]

            if len(artist["identifier"]) == 0:
                self._log.debug("missing identifier for artist {}", name)
                continue

            # XXX: Just use the first MBID returned from the service (is this a good idea?)
            artists[artist["identifier"][0]["mbid"]] = namey

        return artists

    def search_songkick_artists(self, api_key, query):
        url = (self.api_url + "/" + self.search_endpoint).format(
            api_key=urllib.parse.quote_plus(api_key),
            query=urllib.parse.quote_plus(query))

        artists = {}

        for artist in self.paginated_request(url, "artist"):
            name = artist["displayName"]

            if len(artist["identifier"]) == 0:
                self._log.debug("missing identifier for artist {}", name)
                continue

            # XXX: Just use the first MBID returned from the service (is this a good idea?)
            artists[artist["identifier"][0]["mbid"]] = name

        return artists


