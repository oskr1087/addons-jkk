from collections import defaultdict


class BatchBomGraph:
    """Prefetch a multi-level BoM graph with one ORM search per frontier.

    Recursion after prefetch is pure Python. Product-specific BoMs have priority
    over template-wide BoMs. Phantom/normal BoMs are both readable as an
    engineering structure; the caller decides how to supply them.
    """

    MAX_DEPTH = 30

    def __init__(self, env, company):
        self.env = env
        self.company = company
        self._bom_by_product = {}
        self._subcontract_bom_by_product = {}
        self._loaded_products = set()

    def _select_bom(self, product, candidates):
        exact = candidates.filtered(lambda b: b.product_id == product)
        if exact:
            return exact.sorted(key=lambda b: (b.sequence, b.id))[:1]
        generic = candidates.filtered(lambda b: not b.product_id)
        return generic.sorted(key=lambda b: (b.sequence, b.id))[:1]

    def preload(self, products):
        frontier = products
        depth = 0
        while frontier and depth <= self.MAX_DEPTH:
            frontier = frontier.filtered(
                lambda p: p.id not in self._loaded_products
            )
            if not frontier:
                break
            self._loaded_products.update(frontier.ids)

            boms = self.env['mrp.bom'].sudo().search([
                ('company_id', 'in', [False, self.company.id]),
                ('product_tmpl_id', 'in', frontier.product_tmpl_id.ids),
                ('type', 'in', ('normal', 'phantom', 'subcontract')),
            ])
            by_template = defaultdict(lambda: self.env['mrp.bom'])
            for bom in boms:
                by_template[bom.product_tmpl_id.id] |= bom

            next_products = self.env['product.product']
            for product in frontier:
                candidates = by_template[product.product_tmpl_id.id]

                engineering_candidates = candidates.filtered(
                    lambda bom: bom.type in ('normal', 'phantom')
                )
                engineering_bom = self._select_bom(
                    product, engineering_candidates
                )
                self._bom_by_product[product.id] = engineering_bom

                subcontract_candidates = candidates.filtered(
                    lambda bom: bom.type == 'subcontract'
                )
                subcontract_bom = self._select_bom(
                    product, subcontract_candidates
                )
                self._subcontract_bom_by_product[
                    product.id
                ] = subcontract_bom

                # Preload both engineering descendants and subcontracting
                # materials so the snapshot can show the complete tree.
                if engineering_bom:
                    next_products |= engineering_bom.bom_line_ids.mapped(
                        'product_id'
                    )
                if subcontract_bom:
                    next_products |= subcontract_bom.bom_line_ids.mapped(
                        'product_id'
                    )

            frontier = next_products
            depth += 1
        return self

    def bom(self, product):
        """Internal manufacturing/kit engineering BOM only."""
        return self._bom_by_product.get(product.id, self.env['mrp.bom'])

    def subcontract_bom(self, product):
        """Subcontracting BOM, kept separate from internal manufacturing."""
        return self._subcontract_bom_by_product.get(
            product.id, self.env['mrp.bom']
        )

    def all_products(self):
        return self.env['product.product'].browse(list(self._loaded_products))
