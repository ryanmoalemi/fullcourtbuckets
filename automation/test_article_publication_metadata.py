"""Article-specific anchors, disclosure and dated edit metadata survive rebuilds."""
import unittest
from pathlib import Path
import publish_articles as pub
import internal_links as links

class ArticlePublicationMetadata(unittest.TestCase):
    def test_explicit_section_links_stay_in_the_same_tab(self):
        rendered=pub.body_html('## Cap test {#cap-test}\n\n[See cap test](#cap-test)')
        self.assertIn('<h2 class="section-title" id="cap-test">Cap test</h2>',rendered)
        self.assertIn('href="#cap-test">See cap test</a>',rendered)
        self.assertNotIn('target="_blank"',rendered)

    def test_article_specific_disclosure_survives_shared_preparation(self):
        record={'editorialDisclosure':'Research & calculations checked against linked sources.'}
        page=links.ensure_how_made('<article><p class="how-made">Old note</p></article>',record)
        self.assertIn('Research &amp; calculations checked against linked sources.',page)
        self.assertEqual(page.count('class="how-made"'),1)
        self.assertEqual(links.how_made_sentence('',{}),links.HOW_MADE_OTHER_UNLINKED)

    def test_modified_timestamp_preserves_publication_date(self):
        meta={'slug':'test','title':'A test','date':'2026-11-01','updated':'2026-11-08T06:30:21+00:00','editorial_disclosure':'Sources checked.'}
        record=pub.record_for(meta,Path('test'),{'imageFocal':'center 20%'})
        self.assertEqual(record['date'],'2026-11-01')
        self.assertEqual(record['dateModified'],meta['updated'])
        self.assertEqual(record['editorialDisclosure'],'Sources checked.')
        meta['updated']='legacy descriptive note'
        self.assertNotIn('dateModified',pub.record_for(meta,Path('test'),{'imageFocal':'center 20%'}))

if __name__=='__main__': unittest.main()
