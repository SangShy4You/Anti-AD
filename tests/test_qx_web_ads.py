import unittest
import re
from scripts.qx_web_ads import patch_limbo_entry


class WebEntryTests(unittest.TestCase):
    def body(self):
        return '\n'.join([
            'const JS_URL = "https://limbopro.com/Adguard/Adblock4limbo.user.js";',
            'const fc_JS_URL = "https://limbopro.com/Adguard/Adblock4limbo.function.js";',
            'const fd_JS_URL = "https://limbopro.com/Adguard/elementBlocker.user.js";',
            'const agent_JS_URL = "https://limbopro.com/Adguard/isAgent.js";',
            'const autoAdDetector_JS_URL = "https://limbopro.com/Adguard/autoAdDetector.js";',
            '<script type="text/javascript" defer src="${JS_URL}">',
            '<script src="${agent_JS_URL}"></script>', '<script src="${agent_JS_URL}"></script>',
            '<script src="${autoAdDetector_JS_URL}"></script>', '<script src="${autoAdDetector_JS_URL}"></script>',
            'const css = `https://limbopro.com/CSS/${domain}.css`;', '$done({body});', ''])

    def test_retains_working_engines_pins_assets_and_closes_body_tag(self):
        url = 'https://raw.githubusercontent.com/limbopro/Adblock4limbo/' + '1'*40 + '/Adguard/Adblock4limbo.js'
        text, report = patch_limbo_entry(self.body(), url)
        self.assertNotIn('https://limbopro.com/', text)
        self.assertNotIn('agent_JS_URL', text)
        self.assertNotIn('autoAdDetector_JS_URL', text)
        self.assertIn('src="${JS_URL}"></script>', text)
        self.assertIn('@' + '1'*40 + '/CSS/${domain}.css', text)
        self.assertEqual(len(report['browser_assets']), 3)

    def test_changed_declaration_stops_instead_of_silently_dropping_dependencies(self):
        url = 'https://raw.githubusercontent.com/limbopro/Adblock4limbo/' + '1'*40 + '/Adguard/Adblock4limbo.js'
        with self.assertRaises(ValueError):
            patch_limbo_entry(self.body().replace('Adblock4limbo.user.js', 'renamed.js'), url)

    def test_both_injection_templates_keep_three_balanced_working_script_elements(self):
        text = '\n'.join([
            '// Original author and Unicode description: 网页净化',
            'const JS_URL = "https://limbopro.com/Adguard/Adblock4limbo.user.js";',
            'const fc_JS_URL = "https://limbopro.com/Adguard/Adblock4limbo.function.js";',
            'const fd_JS_URL = "https://limbopro.com/Adguard/elementBlocker.user.js";',
            'const agent_JS_URL = "https://limbopro.com/Adguard/isAgent.js";',
            'const autoAdDetector_JS_URL = "https://limbopro.com/Adguard/autoAdDetector.js";',
            'const TITLE_INJECTION_BASE = `',
            '<script src="${autoAdDetector_JS_URL}"></script>',
            '<script src="${JS_URL}"></script>',
            '<script src="${fc_JS_URL}"></script>',
            '<script src="${fd_JS_URL}"></script>',
            '<script src="${agent_JS_URL}"></script>',
            '`;',
            'const BODY_INJECTION_BASE = `',
            '<script src="${autoAdDetector_JS_URL}"></script>',
            '<script type="text/javascript" defer src="${JS_URL}">',
            '<script src="${fc_JS_URL}"></script>',
            '<script src="${fd_JS_URL}"></script>',
            '<script src="${agent_JS_URL}"></script>',
            '</body>', '`;',
            'const css = `https://limbopro.com/CSS/${domain}.css`;',
            'const manualCss = `https://limbopro.com/CSS/limbopro.${domain}.css`;',
            '$done({body});', ''])
        # CRLF input is normalized before patch matching; UTF-8 comments survive.
        patched, report = patch_limbo_entry(text.replace('\n', '\r\n'),
            'https://raw.githubusercontent.com/limbopro/Adblock4limbo/' + 'a'*40 + '/Adguard/Adblock4limbo.js')
        self.assertIn('网页净化', patched)
        for name in ('TITLE_INJECTION_BASE', 'BODY_INJECTION_BASE'):
            template = re.search(r'(?m)^const ' + name + r' = `([\s\S]*?)`;', patched).group(1)
            self.assertEqual(len(re.findall(r'<script\b', template)), 3)
            self.assertEqual(template.count('</script>'), 3)
            self.assertEqual(re.findall(r'src="\$\{(\w+)\}"', template),
                             ['JS_URL', 'fc_JS_URL', 'fd_JS_URL'])
        self.assertIn('@' + 'a'*40 + '/CSS/limbopro.${domain}.css', patched)
        self.assertEqual(report['missing_optional_tags_removed'], ['agent_JS_URL', 'autoAdDetector_JS_URL'])

    def test_upstream_fixes_or_changed_optional_tag_counts_require_review(self):
        url = 'https://raw.githubusercontent.com/limbopro/Adblock4limbo/' + '1'*40 + '/Adguard/Adblock4limbo.js'
        changes = [
            self.body().replace('<script type="text/javascript" defer src="${JS_URL}">\n',
                                '<script type="text/javascript" defer src="${JS_URL}"></script>\n'),
            self.body().replace('<script src="${agent_JS_URL}"></script>\n', '', 1),
            self.body().replace('const fd_JS_URL =', 'const extra = "https://limbopro.com/Adguard/elementBlocker.user.js";\nconst fd_JS_URL ='),
        ]
        for changed in changes:
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                patch_limbo_entry(changed, url)


if __name__ == '__main__':
    unittest.main()
