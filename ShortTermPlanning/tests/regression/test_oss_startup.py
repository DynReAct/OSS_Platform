"""Regression checks for installed analytical costs and auction agent counts."""
import unittest

from dynreact.auction.auction import Auction
from dynreact.base.CostProvider import CostProvider
from dynreact.cost.CostCalculatorImpl import SampleCostProvider
from dynreact.module_loader import instantiate_first_matching


class OssStartupTest(unittest.TestCase):
    def test_analytical_provider_is_discoverable(self):
        from dynreact.base.model import Site
        provider = instantiate_first_matching(
            'dynreact.cost.CostCalculatorImpl', CostProvider, 'sampleuc:costs',
            Site(processes=[], equipment=[], storages=[], material_categories=[]),
            explicit_class_name='SampleCostProvider', do_raise=True,
        )
        self.assertIsInstance(provider, SampleCostProvider)

    def test_material_lists_survive_serialization(self):
        for mode in ('Materials', 'Coils', 'Orders'):
            with self.subTest(mode=mode):
                a = Auction(equip=['FIN02'])
                selected = ['a', 'b', 'c', 'd']
                a.set_lists('regression', selected, mode, selected)
                a = Auction.model_validate_json(a.model_dump_json())
                self.assertEqual(a.smats, selected)
                self.assertEqual(a.lmats, [] if mode == 'Orders' else selected)
                self.assertEqual(a.omats, selected if mode == 'Orders' else [])
                self.assertEqual(len(a.equip) + len(a.smats) + 1, 6)


if __name__ == '__main__':
    unittest.main()
