var ordinal = 0

function unzoom_all() {
    ordinal = 0
    var all = document.getElementsByClassName('target-mag-parent')
    for (var i = 0; i != all.length; ++i) {
        var e = all[i]
        if (e.style.display == 'block') {
            e.style.display = 'none'
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
            ordinal = target.ordinal
            console.log('zoom_panel: ordinal=' + ordinal)
            elem.style.display='block'            
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
    console.log(index)
    if (index >= 0 && index < page_count) {        
        ordinal = 0
        url[url.length-1] = index        
        url = url.join('-') + '.html'
        window.location.href = url
    }
}

function navigate_panel(direction) {
    console.log('navigate_panel: ordinal=' + ordinal)
    if (ordinal) {
        var page = window.location.href.split('/')
        page = page[page.length-1].split('.')[0]
        id = 'reg-' + page + '-' + (ordinal + direction)
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
