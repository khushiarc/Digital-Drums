def mode(data):
    if iter(data) is data:
        data = list(data)
    data = sorted(data)
    last = modev = None
    countmax = i = 0
    while i < len(data):
        if data[i] == last:
            count += 1
        else:
            count = 1
            last = data[i]
        if count > countmax:
            countmax = count
            modev = last
        i += 1
    return modev