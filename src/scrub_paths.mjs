/**
 * Keep host filesystem paths out of recorded measurements.
 *
 * A lane runs pandoc by its resolved absolute path, so node's own
 * "Command failed: <path> -f typst -t json" lands in results/ and from there
 * in the generated pages under docs/. The reader needs the converter and the
 * reason, never the machine it ran on.
 */

/** Replace `binary` with its bare name, then any remaining home directory. */
export function scrubPaths(text, binary) {
    let out = String(text ?? '');
    if (binary && binary.includes('/')) {
        out = out.split(binary).join(binary.slice(binary.lastIndexOf('/') + 1));
    }
    return out.replace(
        /\/(?:home|Users)\/[^/\s:"']+|\/media\/[^/\s:"']+\/[^/\s:"']+/g,
        '~',
    );
}
