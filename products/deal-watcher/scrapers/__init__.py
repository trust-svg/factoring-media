from .yahoo_auction import YahooAuctionScraper
from .mercari import MercariScraper
from .yahoo_fleamarket import YahooFleamarketScraper
from .rakuma import RakumaScraper
from .hardoff import HardoffScraper
from .yahoo_shopping import YahooShoppingScraper
from .rakuten import RakutenScraper

ALL_SCRAPERS = [
    YahooAuctionScraper(),
    MercariScraper(),
    YahooFleamarketScraper(),
    RakumaScraper(),
    HardoffScraper(),
    YahooShoppingScraper(),
    RakutenScraper(),
]
