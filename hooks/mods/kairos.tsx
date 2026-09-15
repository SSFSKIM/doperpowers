import type { On } from 'claude-code'

/**
 * Reads a slash command run as the kairos switch: true for `/kairos`, false
 * for `/kairos off` (or `stop`, `end`), null for any other command. The
 * harness lists a plugin skill under its qualified name too.
 */
export function readToggle(command: string, args: string): boolean | null {
  if (command !== 'kairos' && command !== 'doperpowers:kairos') {
    return null
  }
  return !['off', 'stop', 'end'].includes(args.trim())
}

const BUTTON = 'kairos'

/**
 * Registers the switch. The mode itself stays with the shell hooks beside
 * this folder: `/kairos` carries the skill body into the turn and
 * kairos-toggle.sh records the session id under ~/.claude/kairos, and
 * kairos.sh re-injects the body after compaction. This module only reads that
 * state to draw the button, and runs the command when the button is pressed.
 */
export function registerKairos(on: On) {
  let isOn = false

  on('session.start', async ($, e, next) => {
    const env = await $.env.get('KAIROS')
    if (env === '1' || env === 'true' || env === 'on') {
      isOn = true
    } else {
      const dir = (await $.env.get('KAIROS_DIR')) ?? `${await $.env.get('HOME')}/.claude/kairos`
      isOn = await $.fs.exists(`${dir}/${await $.session.id()}`)
    }
    $.ui.invalidate('ui.render')
    return next(e)
  })

  // A typed `/kairos` and the button's own run alike pass here.
  on('command.run', async ($, e, next) => {
    const toggle = readToggle(e.command, e.args)
    if (toggle !== null && toggle !== isOn) {
      isOn = toggle
      $.ui.invalidate('ui.render')
    }
    return next(e)
  })

  on('ui.render', { component: 'SessionMode' }, ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const others = e.props.modes.join(' & ')
    return (
      <Box>
        {others ? <Text dimColor>{others} & </Text> : null}
        <Button
          key={BUTTON}
          label={isOn ? 'kairos on' : 'kairos off'}
          dimColor={!isOn}
          onPress={() => {}}
        />
      </Box>
    )
  })

  on('ui.press', { element: BUTTON }, async ($, e, next) => {
    const result = await next(e)
    void $.command.run({ command: 'kairos', args: isOn ? 'off' : '' })
    return result
  })
}
