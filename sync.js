async function syncFromJSON() {
  try {
    const response = await fetch('candidatures.json');
    const data = await response.json();
    
    let state = JSON.parse(localStorage.getItem('alternance_bot') || '{}');
    
    state.candidatures = data.candidatures || [];
    
    localStorage.setItem('alternance_bot', JSON.stringify(state));
    
    console.log(`✅ ${state.candidatures.length} candidatures importées !`);
    alert(`✅ Synchronisation réussie !\n${state.candidatures.length} candidatures importées.`);
    
    // Supprimer le reload
    // location.reload();

  } catch (error) {
    console.error('❌ Erreur:', error);
    alert('❌ Erreur : Fichier candidatures.json introuvable ou invalide.');
  }
}
