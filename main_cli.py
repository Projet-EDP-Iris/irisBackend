from app.services.gmail_service import GmailService
import sys

def print_menu(accounts):
    print("\n" + "="*30)
    print("   📧  ASSISTANT EMAIL MANAGER  📧")
    print("="*30)
    
    if accounts:
        print("\nComptes enregistrés :")
        for idx, email in enumerate(accounts, 1):
            print(f"  {idx}. {email}")
            
    print("\nOptions :")
    if accounts:
        print("  [#].  👉 Tapez le numéro du compte pour vous connecter")
    print("  new.  ➕ Ajouter un nouveau compte Gmail")
    print("  q.    🚪 Quitter")
    print("="*30)

def display_emails(gmail):
    print(f"\n📨 Récupération des emails pour {gmail.current_email}...")
    emails = gmail.fetch_recent_emails(5)
    
    if emails:
        print(f"\n{len(emails)} derniers emails :")
        for i, email in enumerate(emails, 1):
            print(f"\n[{i}] {email['subject'][:60]}")
            print(f"    De:     {email['sender']}")
            print(f"    Date:   {email['date']}")
            print(f"    Aperçu: {email['snippet'][:80]}...")
            print("-" * 40)
    else:
        print("📭 Aucun email trouvé.")

def main():
    try:
        gmail_service = GmailService()
        
        while True:
            accounts = gmail_service.list_registered_accounts()
            print_menu(accounts)
            
            choice = input("\n👉 Votre choix : ").strip().lower()
            
            if choice == 'q':
                print("\nAu revoir ! 👋")
                sys.exit(0)
                
            elif choice == 'new':
                try:
                    email = gmail_service.authenticate_new_account()
                    print(f"\n✅ Compte ajouté avec succès : {email}")
                    # Auto-select the new account to show emails immediately
                    display_emails(gmail_service)
                except Exception as e:
                    print(f"\n❌ Erreur lors de l'ajout du compte : {e}")
            
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(accounts):
                    email = accounts[idx]
                    print(f"\n🔑 Connexion à {email}...")
                    if gmail_service.authenticate_existing_account(email):
                        display_emails(gmail_service)
                else:
                    print("\n⚠️  Numéro invalide.")
            else:
                print("\n⚠️  Choix non reconnu.")
            
            print("\nQue voulez-vous faire ?")
            print("  [Entrée] 🔙 Changer de compte (Retour au menu)")
            print("  q.       🚪 Quitter")
            
            next_action = input("\n👉 Votre choix : ").strip().lower()
            if next_action == 'q':
                print("\nAu revoir ! 👋")
                sys.exit(0)

            
    except Exception as e:
        print(f"\n❌ Erreur critique : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
