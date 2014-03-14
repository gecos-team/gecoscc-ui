def created_msg(request, msg, msg_type):
    if not 'messages' in request.session:
        request.session['messages'] = []
    request.session['messages'].append((msg_type, msg))
