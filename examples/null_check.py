"""Example A: the missing None check.

Bug: process_scores() indexes `scores[0]` and iterates `scores` without
ever checking whether `scores` is None. A caller passing None crashes
with TypeError. The fix is a guard at the top of the function.

Demo question to speak (Hinglish): "bro check karo is array me null
check kyun miss ho gaya"
"""


def process_scores(scores):
    """Return the average of a list of scores."""
    total = scores[0]
    for value in scores[1:]:
        total += value
    return total / len(scores)
