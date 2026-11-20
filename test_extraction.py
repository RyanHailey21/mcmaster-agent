from bs4 import BeautifulSoup

from browser import McMasterBrowser


def test_spec_text_preserves_fractions_and_separates_lines():
    soup = BeautifulSoup('''
        <tr class="_product-detail-spec-table-row_hash">
          <td class="_tableCell_hash">End-to-End Length</td>
          <td class="_tableCell_hash"><p>1 <span class="af">7/8</span>"</p></td>
        </tr>
        <tr class="_product-detail-spec-table-row_hash">
          <td class="_tableCell_hash">For Use With</td>
          <td class="_tableCell_hash"><p>Water<br>Air <br> Natural Gas</p></td>
        </tr>
    ''', 'html.parser')
    browser = McMasterBrowser.__new__(McMasterBrowser)

    assert browser._extract_specs(soup) == {
        'End-to-End Length': '1 7/8"',
        'For Use With': 'Water, Air, Natural Gas',
    }


def test_search_omits_generic_image_labels():
    soup = BeautifulSoup('''
        <img src="/47465ee5.png" alt="Spec Image">
        <img src="/6588n101.png" alt="  Threaded Manual On/Off Valves  ">
    ''', 'html.parser')
    browser = McMasterBrowser.__new__(McMasterBrowser)

    products = browser._extract_product_list(soup)
    assert [(p.part_number, p.name) for p in products] == [
        ('6588N101', 'Threaded Manual On/Off Valves'),
    ]
