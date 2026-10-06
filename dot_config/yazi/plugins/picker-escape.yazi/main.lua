--- @sync entry
return {
	entry = function()
		if rt.args.chooser_file then
			-- Do not return the current directory as an accepted selection.
			ya.emit("quit", { ["no-cwd-file"] = true })
		else
			ya.emit("escape", {})
		end
	end,
}
