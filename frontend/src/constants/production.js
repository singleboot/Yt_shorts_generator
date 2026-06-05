export const AI_STYLES = [
  { id: 'none', name: 'Default', icon: '🎨', desc: 'Base model only' },
  { id: 'cozyfelt', name: 'CozyFelt', icon: '🧶', desc: 'Soft felt-textured cozy aesthetic' },
  { id: 'fantasy_painterly', name: 'Fantasy Painterly', icon: '🖌️', desc: 'Rich oil-paint fantasy scenes' },
  { id: 'paper_cut_out_style', name: 'Paper Cut Out', icon: '✂️', desc: 'Layered paper cutout art' },
  { id: 'fantasy_anime', name: 'Fantasy Anime', icon: '🌸', desc: 'Anime-style fantasy worlds' },
  { id: 'cinematic_sci_fi_cyberpunk', name: 'Cyberpunk', icon: '🌃', desc: 'Neon-lit sci-fi dystopia' },
  { id: 'fantasy_realism', name: 'Fantasy Realism', icon: '🗡️', desc: 'Realistic fantasy worlds' },
  { id: 'fantasy_puppet_style', name: 'Puppet', icon: '🎭', desc: 'Stop-motion puppet aesthetic' },
  { id: 'wild_west', name: 'Wild West', icon: '🤠', desc: 'Frontier western style' },
  { id: 'post_apocalyptic', name: 'Post Apocalyptic', icon: '☢️', desc: 'Wasteland, decay, ruin' },
  { id: 'claymation', name: 'Claymation', icon: '🏺', desc: 'Plasticine clay characters' },
  { id: 'pixar_toon', name: 'Pixar Toon', icon: '🎬', desc: '3D animated feature look' },
  { id: 'ghibli', name: 'Ghibli', icon: '🌳', desc: 'Studio Ghibli hand-painted' },
  { id: 'walgro_style', name: 'Walgro', icon: '🎨', desc: 'Bold comic illustration' },
  { id: 'goldenboy', name: 'Goldenboy', icon: '✨', desc: 'Golden cinematic tone' },
  { id: 'golden_age_comic', name: 'Golden Age Comic', icon: '📰', desc: 'Vintage 1940s comic art' },
];

// Mirror of backend app.config.STYLE_LORAS. Shows the user which LoRA file
// will be injected for a given style. Keep in sync with backend changes.
export const STYLE_LORA_PATHS = {
  cozyfelt: 'ltx2/CozyFelt.safetensors',
  fantasy_painterly: 'ltx2/Fantasy_Painterly.safetensors',
  paper_cut_out_style: 'ltx2/PaperCutOutStyle.safetensors',
  fantasy_anime: 'ltx2/Fantasy_Anime.safetensors',
  cinematic_sci_fi_cyberpunk: 'ltx2/Cinematic_sci-fi-cyberpunk.safetensors',
  fantasy_realism: 'ltx2/Fantasy_Realism.safetensors',
  fantasy_puppet_style: 'ltx2/FantasyPuppetStyle.safetensors',
  wild_west: 'ltx2/Wild_West.safetensors',
  post_apocalyptic: 'ltx2/Post_Apocalyptic.safetensors',
  claymation: 'ltx2/Claymation.safetensors',
  pixar_toon: 'ltx2/Pixar_Toon.safetensors',
  ghibli: 'ltx2/ghibli.safetensors',
  walgro_style: 'ltx2/walgro.safetensors',
  goldenboy: 'ltx2/goldenboy.comfy.safetensors',
  golden_age_comic: 'ltx2/GoldenAgeComic.safetensors',
};

export const VOICES = [
  { id: 'aiden', name: 'Aiden', gender: 'Male', locale: 'English' },
  { id: 'dylan', name: 'Dylan', gender: 'Male', locale: 'English' },
  { id: 'eric', name: 'Eric', gender: 'Male', locale: 'English' },
  { id: 'ono_anna', name: 'Ono Anna', gender: 'Female', locale: 'English' },
  { id: 'ryan', name: 'Ryan', gender: 'Male', locale: 'English' },
  { id: 'serena', name: 'Serena', gender: 'Female', locale: 'English' },
  { id: 'sohee', name: 'Sohee', gender: 'Female', locale: 'English' },
  { id: 'uncle_fu', name: 'Uncle Fu', gender: 'Male', locale: 'English' },
  { id: 'vivian', name: 'Vivian', gender: 'Female', locale: 'English' },
];

export const MUSIC_GENRES = [
  { id: 'ambient', name: 'Ambient', emoji: '🌊' },
  { id: 'upbeat', name: 'Upbeat', emoji: '⚡' },
  { id: 'epic', name: 'Epic', emoji: '🎬' },
  { id: 'lofi', name: 'Lo-Fi', emoji: '🎵' },
  { id: 'cinematic', name: 'Cinematic', emoji: '🎭' },
  { id: 'corporate', name: 'Corporate', emoji: '💼' },
  { id: 'none', name: 'None', emoji: '🔇' },
];
