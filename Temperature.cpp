// Auther Hamza Tahir
#include<iostream>
using namespace std;
int main()
{
	/* Write a C/C++ program to read temperature in centigrade and display a suitable message
	 according to temperature state below*/
	 int temp;
	 cout<<"Enter The Temperature : ";
	 cin>>temp;
	 if(temp<0)
	 {
	 	cout<<" Freezing weather ";
	 }
	 else if(temp>0 && temp<=10)
	 {
	 	cout<<" Very Cold Weather ";
	 }
	 else if(temp>10 && temp<=20)
	 {
	 	cout<<" Cold Waether ";
	 }
	 else if(temp>20 && temp<=30)
	 {
	 	cout<<" Normal in temp ";
	 }
	 else if(temp>30 && temp<=40)
	 {
	 	cout<<" Hot ";
	 }
	 else if(temp>40)
	 {
	 	cout<<" Very Hot ";
	 }
}
