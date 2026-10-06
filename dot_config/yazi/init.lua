require("git"):setup()

-- Submit files on double-click only when launched with --chooser-file.
local current_click = Current.click
local last_click

function Current:click(event, up)
	current_click(self, event, up)
	if up then
		return
	end

	local file = self._folder.window[event.y - self._area.y + 1]
	if not rt.args.chooser_file or not event.is_left or not file or file.cha.is_dir then
		last_click = nil
		return
	end

	local now = ya.time()
	local url = tostring(file.url)
	-- Fixed 400 ms threshold; use a configurable interval if accessibility needs differ.
	if last_click and last_click.url == url and last_click.x == event.x and last_click.y == event.y
		and now - last_click.time >= 0 and now - last_click.time <= 0.4 then
		last_click = nil
		ya.emit("open", {})
	else
		last_click = { url = url, x = event.x, y = event.y, time = now }
	end
end
