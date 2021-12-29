#!/usr/bin/python
# -*- coding: utf-8 -*-

import curses
import json
import logging
import os
import re

import sys

logger = logging.getLogger('gwkit')
logger.addHandler(logging.FileHandler('gwkit.log'))
logger.setLevel(logging.INFO)

script_path = os.path.dirname(os.path.realpath(__file__))
kinit_password = '{0}/.kinit_passwd'.format(script_path)
server_list_json_file = '{0}/server_list.json'.format(script_path)


class Context:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.user_idx = 0
        self.keyword = ''
        self.rows = 0
        self.cols = 0
        self.half_cols = 0
        self.top_help_rows = 0
        self.top_win_rows = 0
        self.calc_rows_and_cols()

    def calc_rows_and_cols(self):
        self.rows, self.cols = self.stdscr.getmaxyx()
        self.half_cols = int(self.cols / 2)
        self.top_help_rows = 10
        self.top_win_rows = 3


class HelpWindow:
    def __init__(self, context):
        self.window = curses.newwin(context.top_help_rows, context.cols, 0, 0)
        self.window.border(0)
        self.window.scrollok(True)
        self.window.addstr(0, 5, 'Help')
        self.window.addstr(1, 2, '[/]: change user to rlogin')
        self.window.addstr(2, 2, '[ctrl-n]: register new server     [ctrl-d]: delete server')
        self.window.addstr(3, 2, '[ctrl-e]: modify server           [ctrl-c]: quit or close popup window')
        self.window.addstr(4, 2, '[ctrl-l]: load old gw file        [ctrl-r]: reset popup input')
        self.window.addstr(5, 2, '- registered server will be saved when terminated. (server_list.json)')
        self.window.addstr(6, 2, '- make "~/.kinit_passwd" to execute kinit automatically.')
        self.window.addstr(7, 2, '- enter a keyword to filter the list.')
        self.window.addstr(8, 2, '- search for hosts, tags, and descriptions using case-insensitive keywords.')
        self.window.refresh()


class UserWindow:
    def __init__(self, context):
        self.context = context
        self.users = ['irteam', 'irteamsu']
        self.window = curses.newwin(self.context.top_win_rows, self.context.half_cols, self.context.top_help_rows, 0)
        self.window.scrollok(True)
        self.window.border(0)
        self.window.addstr(1, 2, "user : " + self.get_user())
        self.window.refresh()

    def change_user(self):
        self.context.user_idx = (self.context.user_idx + 1) % 2
        self.window.clear()
        self.window.border(0)
        self.window.addstr(1, 2, "user : " + self.get_user())
        self.window.refresh()

    def get_user(self):
        return self.users[self.context.user_idx]


class KeywordWindow:
    def __init__(self, context):
        self.context = context
        self.window = curses.newwin(self.context.top_win_rows, self.context.half_cols, self.context.top_help_rows, self.context.half_cols)
        self.window.scrollok(True)
        self.window.keypad(True)
        self.window.border(0)
        self.window.addstr(1, 2, "keyword : " + self.context.keyword)
        self.window.refresh()
        self.cursur_x = 13 + len(self.context.keyword)

    def getch(self):
        return self.window.getch()

    def refresh(self):
        self.window.refresh()

    def process(self, key):
        if key == 8 or key == 127 or key == curses.KEY_BACKSPACE:
            if self.cursur_x > 13:
                self.window.addstr("\b \b")
                self.context.keyword = self.context.keyword[:-1]
                self.cursur_x -= 1
        elif key >= 32 and key <= 126:
            self.window.addch(key)
            self.context.keyword += chr(key)
            self.cursur_x += 1


class ServerListWindow:
    def __init__(self, context):
        self.context = context
        self.window = curses.newwin(self.context.rows - self.context.top_help_rows - self.context.top_win_rows,
                                    self.context.cols,
                                    self.context.top_help_rows + self.context.top_win_rows,
                                    0)
        self.window.scrollok(True)
        self.padding = 4

        if os.path.exists(server_list_json_file):
            with open(server_list_json_file, 'r') as f:
                self.servers = sorted(json.load(f), key=lambda s: s['host'])
                self.refresh_max()
        else:
            self.servers = []
            self.max_host = 30
            self.max_tags = 30

        self.filtered_servers = []
        self.selected_server_idx = -1
        self.top = 0
        self.bottom = 0
        self.filter()
        self.refresh()

    def _is_matched(self, server, keyword):
        upper_keyword = keyword.upper()

        if upper_keyword in server['host'].upper():
            return True

        if upper_keyword in server['description'].upper():
            return True

        for tag in map(lambda t: t.upper(), server['tags']):
            if upper_keyword in tag:
                return True

        return False

    def _print_color_text(self, text, index, y, x, width):
        keywords = list(map(lambda k: k.upper(), self.context.keyword.rstrip().split(' ')))
        for k in keywords:
            pattern = re.compile("(" + k + ")", re.IGNORECASE)
            match = pattern.search(text, 0, len(text) - 1)
            if match is None:
                continue

            for group in match.groups():
                text = pattern.sub(' ' + group + ' ', text)

        color_index = 0
        text_length = 0
        words = text.split(' ')
        for word in words:
            color_index = 0
            if index == self.selected_server_idx:
                color_index += 1

            if word.upper() in keywords:
                color_index += 2

            self.window.addstr(y, x + text_length, word, curses.color_pair(color_index))
            text_length += len(word)

        if width > 0 and text_length < width:
            self.window.addstr(y, x + text_length, ''.ljust(width - text_length), curses.color_pair(color_index))

    def load_old_gw_file(self, known_host_path):
        if '.known_hosts' not in known_host_path:
            known_host_path = known_host_path + '/.known_hosts'

        if not os.path.exists(known_host_path):
            return

        with open(known_host_path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                chunks = line.strip().split()
                host = chunks[0].strip()
                description = ' '.join(chunks[1:])
                host = host.strip()
                self.insert_server({
                    'host': host,
                    'description': description,
                    'tags': []
                })

    def refresh_max(self):
        if len(self.servers) > 0:
            self.max_host = max(map(lambda s: len(s['host']), self.servers))
            self.max_tags = max(map(lambda s: len(', '.join(s['tags'])), self.servers))
        else:
            self.servers = []
            self.max_host = 30
            self.max_tags = 30

    def filter(self, selected_server_idx=None):
        self.filtered_servers = self.servers
        self.top = 0
        self.bottom = self.context.rows - self.padding - self.context.top_win_rows - self.context.top_help_rows

        if self.context.keyword != '':
            keywords = self.context.keyword.split(' ')
            for k in keywords:
                self.filtered_servers = list(filter(lambda s: self._is_matched(s, k), self.filtered_servers))

        if selected_server_idx is None or selected_server_idx > len(self.filtered_servers) - 1:
            self.selected_server_idx = -1
        else:
            self.selected_server_idx = selected_server_idx

    def refresh(self):
        DEFAULT_PAD_LEN = 5
        HOST_X = DEFAULT_PAD_LEN
        TAGS_X = self.max_host + DEFAULT_PAD_LEN * 2
        DESC_X = self.max_host + self.max_tags + DEFAULT_PAD_LEN * 3

        self.window.clear()
        self.window.border(0)
        self.window.addstr(0, HOST_X, 'Host')
        self.window.addstr(0, TAGS_X, 'Tags')
        self.window.addstr(0, DESC_X, 'Description')

        for (index, server) in enumerate(self.filtered_servers):
            if index < self.top:
                continue

            if index > self.bottom:
                break

            self._print_color_text(server['host'], index, index - self.top + 2, HOST_X, self.max_host + DEFAULT_PAD_LEN)
            self._print_color_text(', '.join(server['tags']), index, index - self.top + 2, TAGS_X, self.max_tags + DEFAULT_PAD_LEN)
            self._print_color_text(server['description'], index, index - self.top + 2, DESC_X, -1)
        self.window.refresh()

    def select_up(self, delta):
        self.selected_server_idx -= delta
        if self.selected_server_idx < 0:
            self.selected_server_idx = 0

        if self.selected_server_idx < self.top:
            scroll = self.top - self.selected_server_idx
            self.top -= scroll
            self.bottom -= scroll

    def select_down(self, delta):
        self.selected_server_idx += delta
        if self.selected_server_idx > len(self.filtered_servers) - 1:
            self.selected_server_idx = len(self.filtered_servers) - 1

        if self.selected_server_idx > self.bottom:
            scroll = self.selected_server_idx - self.bottom
            self.top += scroll
            self.bottom += scroll

    def connect(self, user):
        if self.selected_server_idx < 0:
            return

        curses.endwin()
        os.system('rlogin -l {0} {1}'.format(user, self.filtered_servers[self.selected_server_idx]['host']))

    def save_to_json(self):
        with open(server_list_json_file, 'w') as f:
            json.dump(self.servers, f)

    def insert_server(self, new_server):
        for s in self.servers:
            if s['host'] == new_server['host']:
                return

        self.servers.insert(0, new_server)
        self.filter()

    def delete_current_server(self):
        if self.selected_server_idx < 0:
            return

        deleted = self.filtered_servers.pop(self.selected_server_idx)
        self.servers = list(filter(lambda s: s['host'] != deleted['host'], self.servers))
        self.filter(self.selected_server_idx)

    def get_current_server(self):
        if self.selected_server_idx < 0:
            return None
        else:
            return self.filtered_servers[self.selected_server_idx]


class InputLabel:
    def __init__(self, window, padding_left, prefix, value=None):
        self.window = window
        self.prefix = prefix
        self.value = ''
        if value is not None:
            self.value = value
        self.min_x = padding_left + len(self.prefix) + 1
        self.x = self.min_x + len(self.value)

    def process_key(self, key):
        if key == 8 or key == 127 or key == curses.KEY_BACKSPACE:
            if self.x > self.min_x:
                self.window.addstr("\b \b")
                self.value = self.value[:-1]
                self.x -= 1
        elif key == 18:
            for i in range(len(self.value)):
                self.window.addstr("\b \b")
                self.value = self.value[:-1]
                self.x -= 1
        elif key >= 32 and key <= 126:
            self.window.addch(key)
            self.value += chr(key)
            self.x += 1

    def print_label(self, y, x):
        self.window.addstr(y, x, self.prefix + " " + self.value)


class LoadOldGwFilePopupWindow:
    def __init__(self, context):
        half_cols = int(context.cols / 2) - 50
        self.window = curses.newwin(3, 100, context.top_help_rows + context.top_win_rows + 4, half_cols)
        self.window.border(0)
        self.window.scrollok(True)
        self.window.addstr(0, 5, 'Load old gateway .known_hosts (.known_host can be omitted)')
        self.window.bkgd(' ', curses.color_pair(5))
        self.path_input_label = InputLabel(self.window, 2, 'Path :', os.path.expanduser('~'))
        self.path_input_label.print_label(1, 2)

    def process(self):
        while (True):
            try:
                c = self.window.getch()
                if c == ord('\n'):
                    return self.path_input_label.value
                else:
                    self.path_input_label.process_key(c)
            except KeyboardInterrupt:
                return None


class ServerPopupWindow:
    def __init__(self, context, servers, host=None, description=None, tags=None):
        half_cols = int(context.cols / 2) - 50
        self.context = context
        self.servers = servers
        self.original_host = host
        self.window = curses.newwin(12, 100, self.context.top_help_rows + self.context.top_win_rows + 4, half_cols)
        self.window.border(0)
        self.window.scrollok(True)
        self.window.keypad(True)
        if self.original_host is None:
            self.window.addstr(0, 5, 'Register')
        else:
            self.window.addstr(0, 5, 'Modify')
        self.window.bkgd(' ', curses.color_pair(5))

        self.padding_top = 2
        self.padding_left = 2

        self.host_input_label = InputLabel(self.window, self.padding_left, 'Host :', host)
        self.description_input_label = InputLabel(self.window, self.padding_left, 'Description :', description)
        self.tags_input_label = InputLabel(self.window, self.padding_left, 'Tags :', '' if tags is None else ' '.join(tags))
        self.input_labels = [self.host_input_label, self.description_input_label, self.tags_input_label]
        self.input_label_idx = 0

        self.host_input_label.print_label(self.padding_top, self.padding_left)
        self.description_input_label.print_label(self.padding_top + 2, self.padding_left)
        self.tags_input_label.print_label(self.padding_top + 4, self.padding_left)

        self._move_cursor(0)

    def _move_cursor(self, delta):
        self.input_label_idx = (self.input_label_idx + delta) % len(self.input_labels)
        input_label = self.input_labels[self.input_label_idx]
        self.window.move(self.padding_top + self.input_label_idx * 2, input_label.x)

    def _process_key(self, key):
        self.input_labels[self.input_label_idx].process_key(key)

    def _is_duplicated_host_exists(self):
        if self.original_host is not None and self.original_host == self.host_input_label.value:
            return False

        for s in self.servers:
            if s['host'] == self.host_input_label.value:
                return True

        return False

    def process(self):
        while (True):
            try:
                c = self.window.getch()
                if c == curses.KEY_UP:
                    self._move_cursor(-1)
                elif c == curses.KEY_DOWN:
                    self._move_cursor(+1)
                elif c == ord('\n'):
                    if not self._is_duplicated_host_exists():
                        return {
                            'host': self.host_input_label.value,
                            'description': self.description_input_label.value,
                            'tags': list(filter(lambda s: s != '', re.split(',| ', self.tags_input_label.value)))
                        }
                    else:
                        self.window.addstr(self.padding_top + 1, self.padding_left, 'Duplicated Host !!!', curses.color_pair(4))
                        self.window.getch()
                        self.window.addstr(self.padding_top + 1, self.padding_left, '                         ')
                        self._move_cursor(0)
                else:
                    self._process_key(c)
            except KeyboardInterrupt:
                return None


def main(stdscr):
    curses.noecho()
    curses.cbreak()
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(0, curses.COLOR_WHITE, -1)
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_YELLOW)
    curses.init_pair(4, curses.COLOR_RED, -1)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)

    context = Context(stdscr)
    HelpWindow(context)
    user_win = UserWindow(context)
    server_list_win = ServerListWindow(context)
    keyword_win = KeywordWindow(context)

    while True:
        try:
            c = keyword_win.getch()
            if c == ord('/'):
                user_win.change_user()
            elif c == curses.KEY_UP:
                server_list_win.select_up(1)
                server_list_win.refresh()
            elif c == curses.KEY_DOWN:
                server_list_win.select_down(1)
                server_list_win.refresh()
            elif c == ord('\n'):
                server_list_win.connect(user_win.get_user())
            elif c == 338:
                server_list_win.select_down(20)
                server_list_win.refresh()
            elif c == 339:
                server_list_win.select_up(20)
                server_list_win.refresh()
            elif c == 4:
                server_list_win.delete_current_server()
                server_list_win.refresh_max()
                server_list_win.refresh()
            elif c == 5:
                current_server = server_list_win.get_current_server()
                if current_server is not None:
                    popup_win = ServerPopupWindow(context,
                                                  server_list_win.servers,
                                                  current_server['host'],
                                                  current_server['description'],
                                                  current_server['tags'])
                    new_server = popup_win.process()
                    if new_server is not None:
                        current_server['host'] = new_server['host']
                        current_server['description'] = new_server['description']
                        current_server['tags'] = new_server['tags']
                        server_list_win.refresh_max()

                    server_list_win.refresh()
            elif c == 14:
                popup_win = ServerPopupWindow(context, server_list_win.servers)
                new_server = popup_win.process()
                if new_server is not None:
                    server_list_win.insert_server(new_server)
                    server_list_win.refresh_max()

                server_list_win.refresh()
            elif c == 12:
                popup_win = LoadOldGwFilePopupWindow(context)
                known_host_path = popup_win.process()
                if known_host_path is not None:
                    server_list_win.load_old_gw_file(known_host_path)

                server_list_win.refresh()
            elif c == curses.KEY_RESIZE:
                context.calc_rows_and_cols()
                user_win = UserWindow(context)
                server_list_win = ServerListWindow(context)
                server_list_win.filter()
                keyword_win = KeywordWindow(context)
            else:
                logger.info(c)
                keyword_win.process(c)
                server_list_win.filter()
                server_list_win.refresh()

            keyword_win.refresh()
        except KeyboardInterrupt:
            curses.endwin()
            server_list_win.save_to_json()
            print('Goodbye :)')
            sys.exit()


if __name__ == '__main__':
    if os.path.exists(kinit_password):
        os.system('cat {0} | kinit'.format(kinit_password))
    else:
        os.system('kinit')
    curses.wrapper(main)