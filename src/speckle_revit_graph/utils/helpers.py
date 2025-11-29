def flatten_dictionary(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        k = k.replace(" ", "_")
        new_key = parent_key + sep + k if parent_key else k
        # print(f"The parent key is {parent_key}, the new key is {new_key}")
        if isinstance(v, dict):
            items.extend(flatten_dictionary(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
