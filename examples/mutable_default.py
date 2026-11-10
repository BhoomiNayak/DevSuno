"""Example F: mutable default argument — the classic Python footgun.

Bug: using [] or {} as a default parameter value. Python evaluates
default arguments exactly once when the function is defined, not on each
call. So every call that doesn't pass the argument shares the SAME list/
dict object — mutations in one call persist into the next call.

This is one of the most famous Python gotchas and trips up experienced
developers too.

Demo question to speak (Hinglish):
  "bro ye function pehli baar theek kaam karta hai but dusri baar
   purana data kyun aa raha hai, list khali honi chahiye thi"
"""


def add_item_to_cart(item, cart=[]) -> list:
    """Add an item to a shopping cart and return it.

    Bug: cart=[] is evaluated once. The same list is reused across every
    call that doesn't pass cart, so items accumulate across unrelated calls.
    """
    cart.append(item)
    return cart


def build_user_profile(name, tags=[], metadata={}) -> dict:
    """Build a user profile dict.

    Bug: tags and metadata share state across calls.
    """
    tags.append("active")              # mutates the shared default
    metadata["last_seen"] = "now"      # mutates the shared default
    return {"name": name, "tags": tags, "metadata": metadata}


# This is what the bug looks like at runtime:
# cart1 = add_item_to_cart("shirt")   -> ["shirt"]          looks fine
# cart2 = add_item_to_cart("shoes")   -> ["shirt", "shoes"] WRONG — should be ["shoes"]
