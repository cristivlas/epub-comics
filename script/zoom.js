function unzoom_all() {
    sessionStorage.setItem('ordinal', 0)
    var all = document.getElementsByClassName('target-mag-parent')
    for (var i = 0; i != all.length; ++i) {
        var e = all[i]
        if (e.style.display == 'block') {
            e.style.display = 'none'
            e.style.visibility = 'hidden'
            return true
        }
    }
    return false
}

function zoom_panel(elem) {
    unzoom_all()
    if (!elem) {
        return
    }
    var magnify = elem.getAttribute('data-app-amzn-magnify')    
    if (magnify) {
        var target = JSON.parse(magnify)
        var id = target.targetId
        elem = document.getElementById(id)
        if (elem) {
            if (elem.style.display == 'block') {
                return
            }            
            sessionStorage.setItem('ordinal', target.ordinal)
            elem.style.display='block'            
            elem.style.visibility = 'visible'
            elem.scrollIntoView()
            elem.focus()
        }
    }
}

function zoom(e) {
    zoom_panel(e.target)
}

function navigate_page(direction) {
    var url = window.location.href.split('.')[0].split('-')
    var index = parseInt(url[url.length-1]) + direction
    if (index < 0 || index >= page_count) {
        // unzoom_all()
    }
    else {
        var ordinal = parseInt(sessionStorage.getItem('ordinal'))
        // zoomed?
        if (ordinal) {
            // save panel ordinal for current page
            sessionStorage.setItem(window.location.href, ordinal)
        }
        if (direction) {
            url[url.length-1] = index
            url = url.join('-') + '.html'

            if (ordinal) {
                var ordinal = sessionStorage.getItem(url)
                if (!ordinal) {
                    // no saved ordinal, start with first on page
                    ordinal = 1
                }
                sessionStorage.setItem('ordinal', ordinal)
            }
            window.location.href = url
        }
    }
}

function navigate_panel(direction) {
    var ordinal = parseInt(sessionStorage.getItem('ordinal'))
    if (ordinal) {
        var page = window.location.href.split('/')
        page = page[page.length-1].split('.')[0]
        var id = 'reg-' + page + '-' + (ordinal + direction)
        elem = document.getElementById(id)
        if (elem) {
            zoom_panel(elem.firstElementChild)
            return
        }
    }
    navigate_page(direction)
}

function key_press(e) {
    if (e.key=='Escape') {
        unzoom_all()
    }
    else if (e.key=='ArrowRight') {
        navigate_panel(1)
    }
    else if (e.key=='ArrowLeft') {
        navigate_panel(-1)
    }
}
