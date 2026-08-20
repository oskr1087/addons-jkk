class ConflictEngine:
    def __init__(self, plan):
        self.plan = plan

    def run(self):
        return self.plan.conflict_ids
