#!/usr/bin/env python

import unittest
import exitwp


class TestExitWP(unittest.TestCase):

    def testExitWP_parse_namespaces(self):
        print('Perform parse_namespaces() test...\n')

        sources = {
            'invalid_filepath': {
                'value': 'foo',
                'result': None,
            },
            'None': {
                'value': None,
                'result': None
            },
            'filepath': {
                'value': 'wordpress-xml/fullpipeumbrella.WordPress.2021-12-30.xml',
                'result': {
                    'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
                    'content': 'http://purl.org/rss/1.0/modules/content/',
                    'wfw': 'http://wellformedweb.org/CommentAPI/',
                    'dc': 'http://purl.org/dc/elements/1.1/',
                    'wp': 'http://wordpress.org/export/1.2/'
                }
            }
        }

        self.assertIsNone(exitwp.parse_namespaces(
            sources['invalid_filepath']['value']))
        self.assertIsNone(exitwp.parse_namespaces(sources['None']['value']))
        self.assertDictEqual(exitwp.parse_namespaces(
            sources['filepath']['value']), sources['filepath']['result'])

        print('\nparse_namespaces() test performed!\n\n')

    def testExitWP_parse_wp_xml(self):
        print('Perform parse_wp_xml() test...\n')

        file = 'foo'
        self.assertIsNone(exitwp.parse_wp_xml(file))

        self.assertIsNone(exitwp.parse_wp_xml(None))
        self.assertIsNone(exitwp.parse_wp_xml(False))
        self.assertIsNone(exitwp.parse_wp_xml(
            '<root><foo:bar>test</foo:bar></root>'))

        print('\nparse_wp_xml() test performed!\n\n')


if __name__ == '__main__':
    unittest.main()
